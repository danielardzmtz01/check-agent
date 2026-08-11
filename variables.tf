variable "project_id" {
  type        = string
  description = "The GCP Project ID where the agent will be deployed."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "The GCP region to deploy resources."
}

variable "service_name" {
  type        = string
  default     = "code-review-agent"
  description = "The name of the Cloud Run service."
}

variable "image_url" {
  type        = string
  description = "The Docker image URL to deploy to Cloud Run."
}

variable "gemini_api_key_secret_id" {
  type        = string
  default     = "gemini-api-key"
  description = "The name of the Secret Manager secret containing the Gemini API Key."
}

variable "staging_bucket_name" {
  type        = string
  description = "The name of the GCS staging bucket to be provisioned for agent deployment."
}

