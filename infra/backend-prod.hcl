bucket         = "terraform-state-ravenpack"
key            = "envs/prod/terraform.tfstate"
region         = "eu-central-1"
dynamodb_table = "terraform-locks"
encrypt        = true
