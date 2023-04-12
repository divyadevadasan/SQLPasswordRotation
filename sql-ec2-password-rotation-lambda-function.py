import boto3
import logging
import os
import time
import re
import json
import secrets
import math

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    arn = event["SecretId"]
    token = event["ClientRequestToken"]
    step = event["Step"]

    # Setup the client
    service_client = boto3.client(
        "secretsmanager", endpoint_url=os.environ["SECRETS_MANAGER_ENDPOINT"])

    # Make sure the version is staged correctly
    metadata = service_client.describe_secret(SecretId=arn)
    if not metadata["RotationEnabled"]:
        logger.error("Secret %s is not enabled for rotation" % arn)
        raise ValueError("Secret %s is not enabled for rotation" % arn)
    versions = metadata["VersionIdsToStages"]
    if token not in versions:
        logger.error(
            "Secret version %s has no stage for rotation of secret %s." % (token, arn))
        raise ValueError(
            "Secret version %s has no stage for rotation of secret %s." % (token, arn))
    if "AWSCURRENT" in versions[token]:
        logger.info(
            "Secret version %s already set as AWSCURRENT for secret %s." % (token, arn))
        return
    elif "AWSPENDING" not in versions[token]:
        logger.error(
            "Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))
        raise ValueError(
            "Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))

    if step == "createSecret":
        create_secret(service_client, arn, token)
    elif step == "setSecret":
        set_secret(service_client, arn, token)
    elif step == "testSecret":
        test_secret(service_client, arn, token)
    elif step == "finishSecret":
        finish_secret(service_client, arn, token)
    else:
        raise ValueError("Invalid step parameter")

    # Boto3 client
    ec2_client = boto3.client("ec2")
    ssm_client = boto3.client("ssm")

    # Getting list of SQL Instance IDs with customer provided 'tag-value' 
    describeInstance = ec2_client.describe_instances(
        Filters=[
            {
                "Name": "tag:sql-password-rotation",
                "Values": [
                    "enabled",
                ]
            }
        ]
    )

    instance_ids = []

    # Fetching instance id of the running instances
    for apiResponse in describeInstance["Reservations"]:
        for instance in apiResponse["Instances"]:
            if instance["State"]["Name"] == "running":
                instance_ids.append(instance["InstanceId"])
                # Looping through instance ids
                for instance_id in instance_ids:
                    # Command to be executed on instance
                    response = ssm_client.send_command(
                        InstanceIds=[instance_id],
                        DocumentName="AWS-RunPowerShellScript",
                        Parameters={
                            "commands": [
                                f'cd C:\SQLInstall',
                                f'Copy-S3Object -BucketName "sql-ec2" -Key "rotate_db_password_sql_multi_user.ps1" -LocalFile "c:/SQLInstall/rotate_db_password_sql_multi_user.ps1"',
                                f'$env:SecretId = "{arn}"',
                                f'Start-Process powershell "c:/SQLInstall/rotate_db_password_sql_multi_user.ps1" -NoNewWindow'
                            ]
                        },
                    )

                    # Fetching command id for the output
                    command_id = response["Command"]["CommandId"]
                    # db_rotate_secret: Lambda: RunPowerShellScript has finished successfully
                    time.sleep(30)

                    # Fetching command output
                    output_message = ssm_client.get_command_invocation(
                        CommandId=command_id, InstanceId=instance_id)
                    output_content = output_message["StandardOutputContent"]
                    ssm_run_command_stderr = output_message["StandardErrorContent"]
                    match = re.search(
                        r'PASSWORDUPDATESUCCESSFUL\b', output_content)

                    if match != -1:
                        logger.info(
                            "Successfully updated Secret on %s." % instance_id)
                    else:
                        logger.info("db_rotate_secret: has failed %s." %
                                    ssm_run_command_stderr)
                        service_client.update_secret_version_stage(
                            SecretId=arn, VersionStage="AWSPENDING", RemoveFromVersionId=token)
                        raise SystemExit(
                            f"Failed {ssm_run_command_stderr} {instance_id}")


def create_secret(service_client, arn, token):
    """ Generate a new secret

    This method first checks for the existence of a secret for the passed in token. If one does not exist, it will generate a
    new secret and save it using the passed in token.

    Args:
        service_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    Raises:
        ValueError: If the current secret is not valid JSON

        KeyError: If the secret json does not contain the expected keys
    """
    # Make sure the current secret exists
    service_client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    # Now try to get the secret version, if that fails, put a new secret
    try:
        service_client.get_secret_value(
            SecretId=arn, VersionId=token, VersionStage="AWSPENDING")
        logger.info("createSecret: Successfully retrieved secret for %s." % arn)
    except service_client.exceptions.ResourceNotFoundException:

        # Get exclude characters from environment variable
        exclude_characters = os.environ["EXCLUDE_CHARACTERS"] if "EXCLUDE_CHARACTERS" in os.environ else '/@"\'\\'

        # Get exclude characters from environment variable
        secret = service_client.get_secret_value(
            SecretId=arn, VersionStage="AWSCURRENT")

        # Fetch SecretString from API call and convert string to dict
        secret_string = json.loads(secret["SecretString"])

        # Checking for all possible allowed prefixes using any()
        prefix = "password"
        count = 0
        for key, val in secret_string.items():
            if key.startswith(prefix):
                count += 1
                # Generate a random password
                secret_string[key] = secrets.token_urlsafe(
                    math.floor(32 / 1.3))

        secret_template = secret_string

        # Put the secret
        service_client.put_secret_value(SecretId=arn, ClientRequestToken=token, SecretString=json.dumps(
            secret_template), VersionStages=["AWSPENDING"])
        logger.info(
            "createSecret: Successfully put secret for ARN %s and version %s." % (arn, token))

def set_secret(service_client, arn, token):
    pass

def test_secret(service_client, arn, token):
    pass

def finish_secret(service_client, arn, token):
    """ Finish the rotation by marking the pending secret as current

    This method moves the secret from the AWSPENDING stage to the AWSCURRENT stage.

    Args:
        service_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    Raises:
        ResourceNotFoundException: If the secret with the specified arn and stage does not exist

    """
    # First describe the secret to get the current version
    metadata = service_client.describe_secret(SecretId=arn)
    current_version = None
    for version in metadata["VersionIdsToStages"]:
        if "AWSCURRENT" in metadata["VersionIdsToStages"][version]:
            if version == token:
                # The correct version is already marked as current, return
                logger.info(
                    "finishSecret: Version %s already marked as AWSCURRENT for %s" % (version, arn))
                return
            current_version = version
            break

    # Finalize by staging the secret version current
    service_client.update_secret_version_stage(
        SecretId=arn, VersionStage="AWSCURRENT", MoveToVersionId=token, RemoveFromVersionId=current_version)
    logger.info(
        "finishSecret: Successfully set AWSCURRENT stage to version %s for secret %s." % (token, arn))
