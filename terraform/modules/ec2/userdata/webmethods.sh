#!/bin/bash
# User data script for webMethods instance

set -e

# Update system
yum update -y

# Install SSM agent (for remote access)
yum install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Install Python for Ansible
yum install -y python3 python3-pip

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Create directory for webMethods
mkdir -p /opt/softwareag

# Tag instance for identification
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
aws ec2 create-tags --resources $INSTANCE_ID --tags Key=Environment,Value=${environment} --region eu-west-1

echo "webMethods instance initialization completed" > /var/log/userdata.log
