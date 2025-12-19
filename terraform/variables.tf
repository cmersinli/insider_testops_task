# variables.tf - Input variables for Terraform

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "insider-testops-task"
}

variable "eks_cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "insider-testops-cluster"
}

variable "ecr_repo_name" {
  description = "ECR repository name"
  type        = string
  default     = "insider-repo"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "eks_cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.34"
}

variable "eks_node_instance_type" {
  description = "Instance type for EKS worker nodes (must be free-tier-eligible)"
  type        = string
  default     = "m7i-flex.large"
}

variable "eks_node_desired_size" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 2
}

variable "ssh_public_key" {
  description = "SSH public key content for EC2 access"
  type        = string
  sensitive   = true
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH to EC2"
  type        = string
  default     = "194.5.236.0/24"

  validation {
    condition     = can(cidrhost(var.allowed_ssh_cidr, 0))
    error_message = "Must be a valid CIDR block."
  }
}
