from langchain.schema import AIMessage, HumanMessage, SystemMessage  # Custom schema definitions for messages
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
                content="""# Role
You are an expert in communication and political science and you are specialized in identifying propaganda techniques in political articles.

# Task
Your task is to carefully analyze the given article and identify any of the 14 propaganda techniques used in the text.
Always be cautious and thorough in your analysis, ensuring not to wrongly identify propaganda techniques.

## Propaganda Techniques
These are the 14 propaganda techniques you will identify, with definitions and examples (in no particular order):
- [Loaded_Language]: Uses specific phrases and words that carry strong emotional impact to affect the audience, e.g., 'a lone lawmaker’s childish shouting.'
- [Name_Calling, Labeling]: Gives a label to the object of the propaganda campaign that the audience either hates or loves, e.g., 'Bush the Lesser.'
- [Repetition]: Repeats the message over and over in the article so that the audience will accept it, e.g., 'Our great leader is the epitome of wisdom. Their decisions are always wise and just.'
- [Exaggeration, Minimization]: Either represents something in an excessive manner or makes something seem less important than it actually is, e.g., 'I was not fighting with her; we were just playing.'
- [Appeal_to_fear-prejudice]: Builds support for an idea by instilling anxiety and/or panic in the audience towards an alternative, e.g., 'stop those refugees; they are terrorists.'
- [Flag-Waving]: Playing on strong national feeling (or with respect to a group, e.g., race, gender, political preference) to justify or promote an action or idea, e.g., 'entering this war will make us have a better future in our country.'
- [Causal_Oversimplification]: Assumes a single reason for an issue when there are multiple causes, e.g., 'If France had not declared war on Germany, World War II would have never happened.'
- [Appeal_to_Authority]: Supposes that a claim is true because a valid authority or expert on the issue supports it, e.g., 'The World Health Organization stated the new medicine is the most effective treatment for the disease.'
- [Slogans]: A brief and striking phrase that contains labeling and stereotyping, e.g., 'Make America great again!'
- [Thought-terminating_Cliches]: Words or phrases that discourage critical thought and useful discussion about a given topic, e.g., 'it is what it is'
- [Whataboutism, Straw_Men, Red_Herring]: Attempts to discredit an opponent’s position by charging them with hypocrisy without directly disproving their argument, e.g., 'They want to preserve the FBI’s reputation.'
- [Black-and-White_Fallacy]: Gives two alternative options as the only possibilities when actually more options exist, e.g., 'You must be a Republican or Democrat'
- [Bandwagon, Reductio_ad_hitlerum]: Justify actions or ideas because everyone else is doing it, or reject them because it's favored by groups despised by the target audience, e.g., 'Would you vote for Clinton as president? 57% say yes.”
- [Doubt]: Questioning the credibility of someone or something, e.g., 'Is he ready to be the Mayor?'

# Instructions
For the given article, please identify all occurrences of the 14 propaganda techniques and provide an explanation of why each passage is considered political propaganda.
Further, return the EXACT passage where the political propaganda can be found.
If no propaganda technique was identified, return an empty dictionary.
If a propaganda technique is used multiple times in the article,, all occurrences MUST be identified and explained.

# Output Format
The output should be valid JSON, with each propaganda technique as a key and a list of occurrences as values.
Each occurrence should have an explanation and the exact passage in the article where the propaganda technique is present.

## Example:
{
    "Loaded_Language": [
        {
            "explanation": "This is an example explanation.",
            "location": "This is the exact passage in the article where the propaganda technique is present."
        },
        {
            "explanation": "This is another example explanation.",
            "location": "This is the exact passage in the article where the propaganda technique is present."
        }
    ],
    "Name_Calling, Labeling": [
        {
            "explanation": "This is another example explanation.",
            "location": "This is the exact passage in the article where the propaganda technique is present."
        }
    ]
}

Here is the article:"""
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
        logging.info("Analyzing article for propaganda techniques...")
        detection_output = self.detect_explain(input_text)
        extracted_techniques_dict = self.format_output(detection_output)
        return extracted_techniques_dict
