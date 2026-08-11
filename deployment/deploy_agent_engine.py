import argparse
import glob
import os
import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
from google.cloud import storage

# Import our agent instance
from code_review_agent.agent import root_agent

def main():
    parser = argparse.ArgumentParser(description="Deploy agent to Vertex AI Reasoning Engine")
    parser.add_argument("--project", help="GCP Project ID")
    parser.add_argument("--location", default="us-central1", help="GCP Location")
    parser.add_argument("--bucket", help="Staging bucket for artifacts")
    args = parser.parse_args()

    project_id = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = args.location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    bucket = args.bucket or os.environ.get("STAGING_BUCKET")

    if not project_id or not bucket:
        print("Error: Project ID and Staging Bucket must be provided.")
        return

    # Normalize bucket name for Storage Client (raw name) vs Vertex AI (gs:// prefix)
    raw_bucket_name = bucket.replace("gs://", "")
    vertex_bucket_uri = f"gs://{raw_bucket_name}"

    # Ensure infrastructure is ready
    print(f"Checking if bucket {raw_bucket_name} exists...")
    storage_client = storage.Client(project=project_id)
    bucket_obj = storage_client.lookup_bucket(raw_bucket_name)
    if not bucket_obj:
        print(f"Bucket {raw_bucket_name} does not exist. Creating in {location}...")
        try:
            storage_client.create_bucket(raw_bucket_name, location=location)
            print(f"Successfully created bucket {raw_bucket_name}")
        except Exception as e:
            print(f"Error creating bucket: {e}")
            return
    else:
        print(f"Bucket {raw_bucket_name} already exists.")

    print(f"Initializing Vertex AI (project={project_id}, location={location}, bucket={vertex_bucket_uri})")
    vertexai.init(project=project_id, location=location, staging_bucket=vertex_bucket_uri)
    
    print("Creating AdkApp wrapper with the agent...")
    adk_app = AdkApp(agent=root_agent)
    
    # Check for build wheel files
    # Note: Make builds wheel file in dist/
    whl_files = glob.glob("dist/*.whl")
    if not whl_files:
        print("Warning: No local wheel file found in dist/. Attempting deployment without dependencies...")
        requirements = []
        extra_packages = []
    else:
        agent_whl_file = whl_files[0]
        print(f"Found local packages to deploy: {agent_whl_file}")
        requirements = [agent_whl_file]
        extra_packages = [agent_whl_file]
    
    print("Deploying to Vertex AI Agent Engine...")
    remote_agent = agent_engines.create(
        adk_app,
        requirements=requirements,
        extra_packages=extra_packages,
    )
    print(f"Successfully deployed: {remote_agent.resource_name}")
    
    # Save the resource name locally
    try:
        agent_id_path = os.path.join(os.path.dirname(__file__), ".agent_id")
        print(f"Saving resource name to {agent_id_path}...")
        with open(agent_id_path, "w") as f:
            f.write(remote_agent.resource_name)
    except Exception as e:
        print(f"Warning: Could not save agent ID to file: {e}")

if __name__ == "__main__":
    main()
