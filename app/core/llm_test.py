from llm_engine.run_local_llm import generate_with_prompt

prompt = """You are an expert performance tester.
Generate a valid JMeter JSON Extractor XML block to extract the `token` value from this JSON response:

{
  "token": "abc123"
}

The output should be in raw XML format that can be added to a .jmx script directly."""
print(generate_with_prompt(prompt))