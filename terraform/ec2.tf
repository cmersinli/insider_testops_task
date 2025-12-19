resource "aws_key_pair" "main" {
  key_name   = "${var.project_name}-key"
  public_key = var.ssh_public_key
}

resource "aws_instance" "kubectl_client" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ec2_kubectl.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_kubectl.name
  key_name               = aws_key_pair.main.key_name

  user_data_base64 = base64encode(<<-USERDATA
#!/bin/bash
set -ex
exec > >(tee /var/log/user-data.log) 2>&1

GIT_REPO="https://github.com/cmersinli/insider_testops_task.git"
HOME_DIR="/home/ec2-user"
PROJECT_DIR="$HOME_DIR/insider_testops_task"
VENV_DIR="$HOME_DIR/venv"
AWS_REGION="${var.aws_region}"
EKS_CLUSTER="${var.eks_cluster_name}"
NAMESPACE="insider-testops"

dnf update -y
dnf install -y git python3.12 python3.12-pip

curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
mv kubectl /usr/local/bin/

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

mkdir -p $HOME_DIR/.kube
aws eks update-kubeconfig --region $AWS_REGION --name $EKS_CLUSTER --kubeconfig $HOME_DIR/.kube/config
chown -R ec2-user:ec2-user $HOME_DIR/.kube

git clone $GIT_REPO $PROJECT_DIR
chown -R ec2-user:ec2-user $PROJECT_DIR

python3.12 -m venv $VENV_DIR
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r $PROJECT_DIR/scripts/requirements.txt
deactivate
chown -R ec2-user:ec2-user $VENV_DIR

cp $PROJECT_DIR/scripts/orchestrator.py $HOME_DIR/orchestrator.py
sed -i '1i#!/home/ec2-user/venv/bin/python3' $HOME_DIR/orchestrator.py
chmod +x $HOME_DIR/orchestrator.py
chown ec2-user:ec2-user $HOME_DIR/orchestrator.py

cat >> $HOME_DIR/.bashrc << 'EOF'

export HELM_CHART_PATH="$HOME/insider_testops_task/helm/insider-testops"
export KUBECONFIG="$HOME/.kube/config"
export PATH="$HOME:$PATH"
source $HOME/venv/bin/activate
alias orchestrator="$HOME/orchestrator.py"
alias k="kubectl"
EOF
chown ec2-user:ec2-user $HOME_DIR/.bashrc

cat >> $HOME_DIR/.bash_profile << 'EOF'

if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi
EOF
chown ec2-user:ec2-user $HOME_DIR/.bash_profile

export KUBECONFIG=$HOME_DIR/.kube/config
sudo -u ec2-user -E kubectl create namespace $NAMESPACE --dry-run=client -o yaml | sudo -u ec2-user -E kubectl apply -f -

echo "Setup completed!"
USERDATA
  )

  tags = {
    Name = "insider-testops-orchestrator"
  }

  depends_on = [
    aws_eks_cluster.main,
    aws_eks_access_policy_association.ec2_kubectl_admin
  ]
}
