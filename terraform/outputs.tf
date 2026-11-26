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
  content         = <<-EOT
    [kiwi]
    kiwi-vm ansible_host=${aws_eip.kiwi.public_ip} ansible_user=ubuntu
  EOT
}

output "data_volume_id" {
  description = "EBS volume id of the optional data disk (set kiwi_data_volume_id in ansible vars); empty when off."
  value       = one(aws_ebs_volume.data[*].id)
}
