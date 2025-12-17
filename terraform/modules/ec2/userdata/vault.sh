#!/bin/bash
# User data script for Vault instance

set -e

yum update -y
yum install -y amazon-ssm-agent python3 python3-pip unzip wget

systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Store KMS key ID and vault bucket for Ansible
echo "${kms_key_id}" > /tmp/kms_key_id
echo "${vault_bucket}" > /tmp/vault_bucket

echo "Vault instance initialization completed" > /var/log/userdata.log
