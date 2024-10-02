from langchain.schema import AIMessage, HumanMessage, SystemMessage  # Custom schema definitions for messages
import prompts
from load_llm import load_llm  # Custom function for loading language models
import json
import logging

RANDOM_SEED = 42

# Class definition for performing propaganda technique detection using OpenAI's models
class OpenAITextClassificationPropagandaInference:
    """
    This class is designed to detect propaganda techniques in text using OpenAI's language models.
    It encapsulates methods for sending structured prompts to the model and parsing the responses.
    """

    def __init__(self, model_name: str):
        """
        Initializes a new instance of the propaganda detection class.

        Args:
            model_name (str): Identifier for the OpenAI model to be used.
        """
        # Initialize the language model with specific parameters
        self.llm = load_llm(model_name,
                            temperature=0,  # Set the temperature parameter for model sampling
                            seed=RANDOM_SEED,  # NOTE currently no supported of the o1 models
                            model_kwargs={
                                "response_format": {"type": "json_object"}
                            })

    def detect_explain(self, input_text: str) -> dict:
        """
        Detects propaganda techniques in the given text and provides explanations for each identified technique.

        Args:
            input_text (str): The article text to analyze.

        Returns:
            str: The model's output containing detected propaganda techniques and explanations.
        """
        # Define the conversation prompt with instructions for the model
        prompt = [
            SystemMessage(
                content=prompts.SYSTEM_PROMPT
            ),
            HumanMessage(
                content=input_text  # The input article text for analysis
            ),
        ]

        # Get the model's output given the prompt
        output = self.llm(prompt)
        return json.loads(output.content)

    def format_output(self, detections: dict) -> dict:
        """
        Parses the model output to extract identified propaganda techniques and their explanations.

        Args:
            input_string (str): Raw string output from the model.

        Returns:
            dict: A dictionary mapping each propaganda technique to its explanation and text evidence.
        """
        extracted_techniques = {}

        # List of known propaganda techniques
        propaganda_techniques = [
            "Loaded_Language",
            "Name_Calling, Labeling",
            "Repetition",
            "Exaggeration, Minimization",
            "Appeal_to_fear-prejudice",
            "Flag-Waving",
            "Causal_Oversimplification",
            "Appeal_to_Authority",
            "Slogans",
            "Thought-terminating_Cliches",
            "Whataboutism, Straw_Men, Red_Herring",
            "Black-and-White_Fallacy",
            "Bandwagon, Reductio_ad_hitlerum",
            "Doubt"
        ]
        for technique in detections.keys():
            if technique in propaganda_techniques:
                if technique not in extracted_techniques:
                    extracted_techniques[technique] = []
                for detection in detections[technique]:
                    extracted_techniques[technique].append({
                        f"explanation": detection["explanation"],
                        "location": detection["location"].strip().strip('"').strip("'")
                    })
            else:
                print(f"Unknown technique detected: {technique}")
        return extracted_techniques

    def analyze_article(self, input_text: str) -> dict:
        """
        Analyzes an article for propaganda techniques, combining detection and formatting of results.

        Args:
            input_text (str): The text of the article to analyze.

        Returns:
            dict: A dictionary containing the detected propaganda techniques and their details.
        """
        try:
            logging.info("Analyzing article for propaganda techniques...")
            detection_output = self.detect_explain(input_text)
            extracted_techniques_dict = self.format_output(detection_output)
            extracted_techniques_dict["status"] = "success"
            return extracted_techniques_dict
        except Exception as e:
            logging.error(f"An error occurred during analysis: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
