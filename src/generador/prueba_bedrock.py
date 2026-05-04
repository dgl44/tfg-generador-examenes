import json

import boto3
from dotenv import load_dotenv

load_dotenv()

client = boto3.client("bedrock-runtime")

response = client.invoke_model( 
    modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0", 
    body=json.dumps({ 
        "anthropic_version": "bedrock-2023-05-31", 
        "max_tokens": 1024, 
        "messages": [{ 
            "role": "user", 
            "content": "Tell me a short story about a robot. In spanish" 
        }] 
    }) 
)  

result = json.loads(response["body"].read()) 
print(result["content"][0]["text"])