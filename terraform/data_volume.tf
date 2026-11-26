# Optional separate disk for the database, so replacing the VM does not take
# the data with it. Off by default (data_volume_size_gb = 0).
# No prevent_destroy: it would block the end-of-month `terraform destroy`.
# Daily DLM snapshots (snapshots.tf) cover it through the Snapshot tag.
resource "aws_ebs_volume" "data" {
  count = var.data_volume_size_gb > 0 ? 1 : 0

  availability_zone = aws_instance.kiwi.availability_zone
  size              = var.data_volume_size_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name     = "${var.project_tag}-data"
    Snapshot = "daily"
  }
}

resource "aws_volume_attachment" "data" {
  count = var.data_volume_size_gb > 0 ? 1 : 0

  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data[0].id
  instance_id = aws_instance.kiwi.id
}
