# Load the SQL Server Management Objects (SMO) 

$version = (Invoke-Sqlcmd -Query 'SELECT @@VERSION;').Column1
if ($version -like 'Microsoft SQL Server 2016*') {
    $sqlRegistryPath = 'HKLM:\SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.SqlServer.Management.PowerShell.sqlps130'
    $sqlPowerShellModulePath = 'C:\Program Files (x86)\Microsoft SQL Server\130\Tools\PowerShell\Modules\SQLPS'
}
elseif ($version -like 'Microsoft SQL Server 2017*') {
    $sqlRegistryPath = 'HKLM:\SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.SqlServer.Management.PowerShell.sqlps140'
    $sqlPowerShellModulePath = 'C:\Program Files (x86)\Microsoft SQL Server\140\Tools\PowerShell\Modules\SQLPS'
}
elseif ($version -like 'Microsoft SQL Server 2019*') {
    $sqlRegistryPath = 'HKLM:\SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.SqlServer.Management.PowerShell.sqlps150'
    $sqlPowerShellModulePath = 'C:\Program Files (x86)\Microsoft SQL Server\150\Tools\PowerShell\Modules\SQLPS'
}
else {
    throw 'SQL Server version not supported'
}

if ((Test-Path $sqlRegistryPath) -eq $false) {  
    throw 'SQL Server Provider for Windows PowerShell is not installed.'
}

@('Microsoft.SqlServer.Management.Common',  
    'Microsoft.SqlServer.Smo',
    'Microsoft.SqlServer.Dmf',  
    'Microsoft.SqlServer.Instapi',
    'Microsoft.SqlServer.SqlWmiManagement',  
    'Microsoft.SqlServer.ConnectionInfo',  
    'Microsoft.SqlServer.SmoExtended',  
    'Microsoft.SqlServer.SqlTDiagM',  
    'Microsoft.SqlServer.SString',  
    'Microsoft.SqlServer.Management.RegisteredServers',  
    'Microsoft.SqlServer.Management.Sdk.Sfc',  
    'Microsoft.SqlServer.SqlEnum',  
    'Microsoft.SqlServer.RegSvrEnum',  
    'Microsoft.SqlServer.WmiEnum',  
    'Microsoft.SqlServer.ServiceBrokerEnum',  
    'Microsoft.SqlServer.ConnectionInfoExtended',  
    'Microsoft.SqlServer.Management.Collector',  
    'Microsoft.SqlServer.Management.CollectorEnum',  
    'Microsoft.SqlServer.Management.Dac',  
    'Microsoft.SqlServer.Management.DacEnum',  
    'Microsoft.SqlServer.Management.Utility') | ForEach-Object {
    [Reflection.Assembly]::LoadWithPartialName($_)  
}

Update-FormatData -PrependPath (Join-Path $sqlPowerShellModulePath 'SQLProvider.Format.ps1xml')

#Fetch Secret Credentials from Secret Manager

$oldSecretString = (Get-SECSecretValue -SecretId $env:SecretId  -Select SecretString -VersionStage 'AWSCURRENT' | ConvertFrom-Json)
$usercount = $oldSecretString.totalusers
$secretString = (Get-SECSecretValue -SecretId $env:SecretId  -Select SecretString -VersionStage 'AWSPENDING' | ConvertFrom-Json)

#Rotate Password of each user

For ($i = 1; $i -le $usercount; $i++) {
    $password = "password" + $i
    $oldPassword = $oldSecretString.$password
    $name = "loginname" + $i
    $loginName = $secretString.$name
    $newPassword = $secretString.$password
 
    #Create a new SqlConnection object
    
    $sqlConnection = New-Object System.Data.SqlClient.SqlConnection
    $sqlConnection.ConnectionString = "Server=$env:computername; User ID = $loginName; Password = $oldPassword;"
    Write-Host "Trying to connect to SQL Server instance on $env:computername..." -NoNewline
 
    $sqlConnection.Open()
    $sql = "ALTER LOGIN [$loginName] WITH PASSWORD = '$newPassword' OLD_PASSWORD = '$oldPassword';"
 
    $cmd = New-Object System.Data.Sqlclient.Sqlcommand($null, $sqlConnection)
    $cmd.CommandText = $sql
    $null = $cmd.ExecuteNonQuery()
    $cmd.Dispose()

    Write-Host 'Password for Login:'$loginName' changed successfully on server:'$env:computername' '
    Write-Host 'PASSWORDUPDATESUCCESSFUL'
    
    $sqlConnection.Close()
    $sqlConnection.Dispose()

}
