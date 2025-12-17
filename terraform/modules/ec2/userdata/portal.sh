#!/bin/bash
# User data script for Portal instance

set -e

yum update -y
yum install -y amazon-ssm-agent python3 python3-pip

systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Create directory for Portal
mkdir -p /opt/softwareag/portal

# Store webMethods IP for later configuration
echo "${webmethods_ip}" > /tmp/webmethods_ip

echo "Portal instance initialization completed" > /var/log/userdata.log
