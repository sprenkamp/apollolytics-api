import os

from dotenv import load_dotenv

load_dotenv()


def load_llm(model_name, api_key=None, **kwargs):
    """
    Load the LLM from the model_name and optional keyword arguments.
    """

    if "gpt" in model_name:
        from langchain_openai import ChatOpenAI

        # Check if custom settings were provided in kwargs, 
        # otherwise use defaults
        temperature = kwargs.get('temperature', 0)
        max_tokens = kwargs.get('max_tokens', None)
        model_kwargs = kwargs.get('model_kwargs', {})
        seed = kwargs.get('seed', None)
        api_key = api_key or os.getenv("OPENAI_API_KEY")

        llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
            seed=seed,
            api_key=api_key
        )

    elif 'gemini' in model_name:
        from langchain_google_genai import \
            ChatGoogleGenerativeAI  # NOTE needs debug -> ValueError: Your location is not supported by google-generativeai at the moment. Try to use ChatVertexAI LLM from langchain_google_vertexai.
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        llm = ChatGoogleGenerativeAI(model=model_name,
                                     convert_system_message_to_human=True,
                                     google_api_key=api_key
                                     # NOTE currently no support for custom system messages
                                     )
    else:
        raise ValueError(f"Model {model_name} not found")

    return llm
