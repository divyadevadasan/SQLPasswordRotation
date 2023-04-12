# SQL Password Rotation
===

Prerequisites
---

- Lambda function in this solution filters the SQL instances based on a custom tag. Customers should tag their EC2 SQL instances with the following tag key-value:
    tag-key: "sql-password-rotation"
    tag-value: "enabled"
- Get Secret Name/Secret ARN and rotation schedule (30,60,90 day automatic rotation) config details from the customer.

Automated credential rotating for SQL Auth users
---
Solution Workflow
---

- Lambda function generates a new password and updates the secret string.
- Lambda then filters the EC2 SQL cluster instances based on the mentioned "tag-value" and executes the PowerShell script stored in each of the EC2 instance via SSM.
- Once the SSM document is executed successfully, the Lambda verifies if the SSM command was executed successfully and completes the rotation.

Onboarding Steps
---

CloudFormation stack deployment:

- Upload the following files under the root folder of an S3 bucket:
    CloudFormation template: "sql-password-rotation-onboarding-template.json"
    Lambda zip file: "sql_user_rotation_lambda_function.zip"
    PowerShell Script: "sql-ec2-password-rotation-script.ps1"

- Deploy the JSON file template uploaded to S3 bucket via CloudFormation console.
- Under 'Parameters' console, retain the default values of the parameters. 

Secrets Manager Console:

- Select the secret provided by the customer. Under 'Rotation Configuration', select "Edit".
- Update the rotation schedule (30,60,90 day automatic rotation) as per customer requirement.
- Select rotation function "OOD-SQLPasswordRotation".
- Click "Save". This will immediately trigger a password rotation.

Verify Password Rotation:

- After initiating the password rotation, confirm if the rotation has been successful using CloudWatch logs.
- Navigate to the CloudWatch console.
- Under log-group "/aws/lambda/SQLPasswordRotation", verify if the latest log-stream has the following logs:
    "finishSecret: Successfully set AWSCURRENT stage to version"
    "Successfully updated Secret on <instance-id>"

---

Secrets Rotation can also be triggered manually by the customer or by AMS Operations (on customer's request) through the Secrets Manager console in between automatic rotation periods.

