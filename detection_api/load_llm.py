from dotenv import load_dotenv
load_dotenv()

def load_llm(model_name, **kwargs):  # Add **kwargs to accept any arguments
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

        llm = ChatOpenAI(
            model_name=model_name, 
            temperature=temperature,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
            seed=seed
            )

    elif 'gemini' in model_name:
        from langchain_google_genai import ChatGoogleGenerativeAI #NOTE needs debug -> ValueError: Your location is not supported by google-generativeai at the moment. Try to use ChatVertexAI LLM from langchain_google_vertexai. 
        llm = ChatGoogleGenerativeAI(model=model_name, 
                                     convert_system_message_to_human=True #NOTE currently no support for custom system messages
                                     )
    else:
        raise ValueError(f"Model {model_name} not found")

    return llm

if __name__ == "__main__":
    # Load with default settings
    llm = load_llm(model_name="gpt-4-turbo-preview")  

    # Load with custom settings
    llm = load_llm(
        model_name="gpt-4-turbo-preview",
        temperature=0,
        max_tokens=1500,
        model_kwargs={
            "top_p": 1,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
    )

    print(llm.invoke("Hello, how are you?"))