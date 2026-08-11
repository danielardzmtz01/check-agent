output "service_url" {
  value       = google_cloud_run_v2_service.agent_service.uri
  description = "The URL of the deployed Cloud Run service hosting the agent."
}
