variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (2 GB RAM needed for Kiwi + MariaDB)."
  type        = string
  default     = "t3.small"
}

variable "admin_cidr" {
  description = "Your public IP as a /32 CIDR; the only source allowed to SSH."
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && endswith(var.admin_cidr, "/32")
    error_message = "admin_cidr must be a single IPv4 address in /32 form, e.g. 203.0.113.10/32."
  }
}

variable "ssh_public_key_path" {
  description = "Path to the PUBLIC key file (the private key never leaves your machine)."
  type        = string
}

variable "project_tag" {
  description = "Value of the Project tag."
  type        = string
  default     = "kiwi-tcms"
}

variable "expires_tag" {
  description = "Value of the Expires tag (a date reminding you to destroy)."
  type        = string
}

variable "alert_email" {
  description = "Email that receives budget alerts."
  type        = string
  sensitive   = true
}

variable "budget_limit_usd" {
  description = "Monthly budget limit in USD."
  type        = number
  default     = 30
}
