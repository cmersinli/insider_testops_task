# eks.tf - EKS Cluster and Node Group

# EKS Cluster (Private access only - accessible from EC2 instance only)
resource "aws_eks_cluster" "main" {
  name     = var.eks_cluster_name
  version  = var.eks_cluster_version
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids              = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    endpoint_public_access  = false
    endpoint_private_access = true
    security_group_ids      = [aws_security_group.eks_cluster.id]
  }

  access_config {
    authentication_mode = "API_AND_CONFIG_MAP"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy
  ]

  tags = {
    Name = var.eks_cluster_name
  }
}

# Launch Template for EKS Node Group (to set Name tag on EC2 instances)
resource "aws_launch_template" "eks_nodes" {
  name = "${var.project_name}-eks-node-template"

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "insider-testops-eks-node"
    }
  }

  tag_specifications {
    resource_type = "volume"
    tags = {
      Name = "insider-testops-eks-node-volume"
    }
  }
}

# EKS Node Group (multi-node in Subnet A)
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn

  # Single subnet - all nodes in Subnet A
  subnet_ids = [aws_subnet.public_a.id]

  instance_types = [var.eks_node_instance_type]

  launch_template {
    id      = aws_launch_template.eks_nodes.id
    version = aws_launch_template.eks_nodes.latest_version
  }

  scaling_config {
    desired_size = var.eks_node_desired_size
    max_size     = 5
    min_size     = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry
  ]

  tags = {
    Name = "${var.project_name}-node-group"
  }
}

# EKS Access Entry for EC2 kubectl client
resource "aws_eks_access_entry" "ec2_kubectl" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.ec2_kubectl.arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "ec2_kubectl_admin" {
  cluster_name  = aws_eks_cluster.main.name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = aws_iam_role.ec2_kubectl.arn

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.ec2_kubectl]
}
