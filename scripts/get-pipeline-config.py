import boto3
import json
import argparse
import os
import sys

def fetch_pipeline_config(pipeline_name, region):
    try:
        client = boto3.client("codepipeline", region_name=region)
        response = client.get_pipeline(name=pipeline_name)
        print(json.dumps(response, indent=2, default=str))
        stages = response["pipeline"]["stages"]

        config = []
        for stage in stages:
            for action in stage["actions"]:
                config.append({
                    "stage_name": stage["name"],
                    "action_name": action["name"],
                    "provider": action["actionTypeId"]["provider"],
                    "configuration": action.get("configuration", {}),
                })
        return config
    except Exception as e:
        print(f"❌ Error fetching pipeline config: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-name", required=True, help="Name of the CodePipeline")
    parser.add_argument("--region", required=True, help="AWS region to use")
    parser.add_argument("--output-dir", default="pipeline_config", help="Output directory")
    args = parser.parse_args()
    config = fetch_pipeline_config(args.pipeline_name, args.region)
    try:
        os.makedirs(args.output_dir, exist_ok=True)
        output_file = os.path.join(args.output_dir, "stages.json")
        with open(output_file, "w") as f:
            json.dump({"pipeline_name": args.pipeline_name, "stages": config}, f, indent=2)
        print(f"✅ Pipeline configuration written to {output_file}")
    except Exception as e:
        print(f"❌ Error writing config file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()