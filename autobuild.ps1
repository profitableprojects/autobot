# Versiyon bilgisini oku
$versionFile = "./version.txt"
$version = Get-Content $versionFile
$versionParts = $version.Split('.')
$minorVersion = [int]$versionParts[2]
$newMinorVersion = $minorVersion + 1
$newVersion = "$($versionParts[0]).$($versionParts[1]).$newMinorVersion"

# Yeni versiyon ile Docker imajlarını build et
docker build -t nvrbox/autobot:$newVersion -t nvrbox/autobot:latest -f ./BotDockerfile . --no-cache
docker build -t nvrbox/autoschedule:$newVersion -t nvrbox/autoschedule:latest -f ./SchDockerfile . --no-cache

# Docker Hub'a push et
docker push nvrbox/autobot:$newVersion
docker push nvrbox/autobot:latest
docker push nvrbox/autoschedule:$newVersion
docker push nvrbox/autoschedule:latest

# Yeni versiyonu kaydet
# Set-Content -Path $versionFile -Value $newVersion
