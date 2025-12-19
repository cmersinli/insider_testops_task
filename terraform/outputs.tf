# outputs.tf - Output values

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "ec2_ami_id" {
  description = "AMI ID used for EC2 (Amazon Linux 2023)"
  value       = data.aws_ami.amazon_linux.id
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_version" {
  description = "EKS cluster Kubernetes version"
  value       = aws_eks_cluster.main.version
}

output "ec2_public_ip" {
  description = "Public IP of EC2 kubectl client"
  value       = aws_instance.kubectl_client.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS of EC2 kubectl client"
  value       = aws_instance.kubectl_client.public_dns
}

output "ssh_command" {
  description = "SSH command to connect to EC2 (Amazon Linux 2023)"
  value       = "ssh ec2-user@${aws_instance.kubectl_client.public_ip}"
}

output "kubectl_config_command" {
  description = "Command to configure kubectl on EC2"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}

# ECR Outputs
output "ecr_repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.main.name
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.main.repository_url
}

output "ecr_registry_id" {
  description = "ECR registry ID"
  value       = aws_ecr_repository.main.registry_id
}

output "docker_login_command" {
  description = "Command to login to ECR"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.main.repository_url}"
}
