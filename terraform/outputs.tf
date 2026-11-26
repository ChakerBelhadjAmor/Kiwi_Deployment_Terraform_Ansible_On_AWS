output "public_ip" {
  description = "Elastic IP of the Kiwi VM."
  value       = aws_eip.kiwi.public_ip
}

output "ssh_command" {
  description = "SSH into the VM (key path assumed from the setup steps)."
  value       = "ssh -i ~/.ssh/kiwi_aws ubuntu@${aws_eip.kiwi.public_ip}"
}

# Rendered inventory for Ansible; gitignored (ansible/inventory/*).
resource "local_file" "ansible_inventory" {
  filename        = "${path.module}/../ansible/inventory/hosts.ini"
  file_permission = "0600"
  # With ssh_ingress_enabled = false, Ansible reaches the VM through SSM; ansible_host stays
  # the Elastic IP because the Caddy role compares it with the DNS answer.
  content = "[kiwi]\nkiwi-vm ansible_host=${aws_eip.kiwi.public_ip} ansible_user=ubuntu${var.ssh_ingress_enabled ? "" : " ansible_ssh_common_args='-o ProxyCommand=\"aws ssm start-session --target ${aws_instance.kiwi.id} --region ${var.region} --document-name AWS-StartSSHSession --parameters portNumber=%p\"'"}\n"
}

output "instance_id" {
  description = "EC2 instance id (for SSM Session Manager)."
  value       = aws_instance.kiwi.id
}

output "ssm_shell_command" {
  description = "Shell on the VM through SSM, no open port 22 needed."
  value       = "aws ssm start-session --target ${aws_instance.kiwi.id} --region ${var.region}"
}

output "ssm_ssh_config" {
  description = "Add to ~/.ssh/config to SSH (and run Ansible) through SSM instead of port 22."
  value       = <<-EOT
    Host ${aws_instance.kiwi.id}
      User ubuntu
      IdentityFile ~/.ssh/kiwi_aws
      ProxyCommand aws ssm start-session --target %h --region ${var.region} --document-name AWS-StartSSHSession --parameters portNumber=%p
  EOT
}
