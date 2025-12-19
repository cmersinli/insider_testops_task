# security-groups.tf - Security groups for EKS and EC2

# EKS Cluster Security Group
resource "aws_security_group" "eks_cluster" {
  name        = "${var.project_name}-eks-cluster-sg"
  description = "Security group for EKS cluster"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-eks-cluster-sg"
  }
}

# EC2 Security Group
resource "aws_security_group" "ec2_kubectl" {
  name        = "${var.project_name}-ec2-kubectl-sg"
  description = "Security group for EC2 kubectl client"
  vpc_id      = aws_vpc.main.id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
    description = "SSH access"
  }

  # All outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ec2-kubectl-sg"
  }
}

# Allow EC2 to access EKS cluster
resource "aws_security_group_rule" "eks_cluster_ingress_ec2" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ec2_kubectl.id
  security_group_id        = aws_security_group.eks_cluster.id
  description              = "Allow EC2 kubectl client to access EKS API"
}
