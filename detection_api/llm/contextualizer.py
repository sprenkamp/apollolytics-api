import logging
import os
import time

import pandas as pd
from dotenv import load_dotenv
from langchain import hub
from langchain.agents import Tool
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import BaseTool
from llm.load_llm import load_llm

from llm.google_retriever import InformationRetrieval

# Load environment variables, including API keys for Google and OpenAI.
load_dotenv()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "default_cse_id")
GOOGLE_APIKEY = os.getenv("GOOGLE_API_KEY", "default_api_key")

# Load excluded URLs from a CSV file
fake = pd.read_csv("llm/ressources/mediabiasfactcheck_fakenews.csv")
fake = fake[fake["Traffic/Popularity"] != "Minimal Traffic"]
excluded_sites = fake["source_link"].apply(lambda x: x.split("//")[-1].split("www.")[-1].split("/")[0])


def render_text_description(tools: list[BaseTool]) -> str:
    """Render the tool name and description in plain text.

    Args:
        tools: The tools to render.

    Returns:
        The rendered text.

    Output will be in the format of:

    .. code-block:: markdown

        search: This tool is used for search
        calculator: This tool is used for math
    """
    descriptions = []
    for tool in tools:
        description = f"<tool>\n{tool.name}:\n{tool.description}\n</tool>"
        descriptions.append(description)
    return "\n".join(descriptions)


google_description = """Get previews of the top google search results to get more information about the statement. The function always returns the next 10 results and can be called multiple times. If initial results seem unrelated you may use quotation marks to search for an exact phrase. Use a minus sign to exclude a word from the search.  Use before:date and after:date to search for results within a specific time period. Do not google the entire statement verbatim."""


def get_prompt(date, originator):
    prompt = hub.pull("hwchase17/react")

    prompt_template = """You are an expert contextualizer tasked to expanding and enriching understanding around potentially misleading statements to make sure users are safe and well informed.
Your role is to provide balanced, accurate, concise, and helpful context about a given statement.

You have access to the following tools for your research:
<tools>
{tools}
</tools>

You may use each tool up to three times.

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat 3 times)
Thought: I now have sufficient information to provide context for the user.
Final Answer: The context demanded by the user.

**Final Response Format:**
- **Context:** (Provide a precise, concise, and factual summary of the topic, incorporating context from the sources)
- **Warning:** (Explain potential risks of misinformation precisely, including how the statement might be misleading and what important context it might be missing)
- **Sources:** (List all important sources by their reference numbers, e.g., [1], [2], [3])

**Example Final Answer in case no results are found:**
Context: No relevant information found.
Warning: The statement may not be widely discussed or may not have been indexed by search engines.
Sources: None

**Example Final Answer:**  
Context: Electric vehicles (EVs) produce fewer greenhouse gas emissions over their lifetime compared to gasoline-powered cars, according to studies [1], [2]. EVs emit no tailpipe emissions and are more efficient in energy use. However, their production, particularly the manufacturing of batteries, involves significant environmental impact due to energy-intensive processes and raw material extraction [3].
Warning: Statements claiming that EVs are "worse for the environment" may focus exclusively on production emissions, ignoring the substantial operational emissions savings during usage. Conversely, claims that EVs are "entirely green" may overlook the environmental impacts of mining lithium, cobalt, and other materials used in battery production.
Sources: 
- [1] EPA Report on Electric Vehicle Myths (2023-Aug)
- [2] MIT Climate Portal Analysis (2024-Jan)
- [3] Environmental Impact Study (2023-Dec)
    
Begin your analysis now!

Question:
Contextualise the statement: '{statement}'{originator_section}{date_section}
Thought:{agent_scratchpad}"""
    date_section = ""
    originator_section = ""
    if date:
        date_section = " on {date}"
    if originator:
        originator_section = " made by {originator}"
    prompt_template = prompt_template.replace("{date_section}", date_section)
    prompt_template = prompt_template.replace("{originator_section}", originator_section)

    prompt.template = prompt_template
    return prompt


class Contextualizer:
    def __init__(self, model_name, cse_id=GOOGLE_CSE_ID, api_key=GOOGLE_APIKEY):
        self.llm = load_llm(model_name,
                            max_tokens=4096,
                            temperature=0,
                            streaming=True)

    async def seems_factual(self, statement):
        """
        Determines whether a given statement seems to be a factual statement or an opinion, with a focus on identifying
        statements that could be related to propaganda or disinformation. This function classifies the statement based
        on how fact-like it appears, not on its actual truthfulness. It is particularly useful in contexts where the
        distinction between misleading factual statements and clear opinions is critical.

        :param statement: The statement to classify as seeming fact or opinion, with a consideration for propaganda and disinformation.
        :return: True if the statement seems to be a factual statement (or is designed to appear as such), False if it seems to be an opinion.
        """
        try:
            from langchain.chains import create_tagging_chain
            # Adjust the grading schema to include examples related to propaganda and disinformation.
            grading_schema = {
                "properties": {
                    "fact_label": {
                        "type": "string",
                        "enum": ['0', '1'],
                        # '0' for opinions or statements not attempting to appear factual, '1' for statements that appear factual.
                        "description": "Classify the given statement with an emphasis on identifying potential propaganda or disinformation. \n"
                                       "0: Opinions (e.g., 'Country X's leaders are the best in the world.', 'Only fools believe in climate change.')\n"
                                       "1: Statement Appears Factual or Misleadingly Factual (e.g., 'Country Y has the highest crime rate due to its immigration policies.', 'Recent studies show that vaccines are more harmful than previously thought.', '9/11 was an inside job.')\n"
                                       "Choose '0' or '1' based on whether the statement seems to be presenting a fact or an opinion, with an eye for potentially misleading information."
                    },
                },
                "required": ["fact_label"],
            }

            # Classify the statement with a focus on its appearance as factual or opinionated, considering propaganda and disinformation.
            output_grading = create_tagging_chain(grading_schema, self.llm).run(statement)

            # Interpret the classification result as a boolean value: True for '1' (Seems Factual or Misleadingly Factual) and False for '0' (Opinion or Clearly Biased).
            return output_grading["fact_label"] == '1'
        except Exception as e:
            logging.error(f"Failed to classify statement: {statement} - {str(e)}")
            return False

    def identify_seemingly_factual(self, text):
        """
        Identifies factual information in a given text, with a focus on identifying statements that could be related to propaganda or disinformation.
        This function classifies the statement based on how fact-like it appears, not on its actual truthfulness. The LLM then returns quotes from the text that seem factual.

        :param text: The text to analyze for factual information.
        :return: A list of quotes from the text that seem to be factual statements (or are designed to appear as such).
        """
        from langchain.schema import HumanMessage, SystemMessage
        prompt = [
            SystemMessage(content="""Please read the following text carefully. Identify and return any segments that present information which appears factual, or is designed to appear as such, especially in the context of potential propaganda or disinformation. Please provide the full quotes from the text, remember to return enough content in quote so in a next step the statement can be contextualized, so quotes can span over multiple sentences if needed to be contextualized usefully. A quote should span over a whole sentence at least. If no such segments are found, return 'No factual segments found.' The ouput should be a list of quotes, with each quote on a new line, e.g.:
            Quote1
            Quote2
            Quote3 and so on"""),
            HumanMessage(content=text),
        ]

        output = self.llm(prompt)
        results_lst = output.content.split("\n")
        return results_lst

    async def process_statement(self, statement, date=None, originator=None):
        """
        Processes a given statement to perform contextualization, utilizing both Google Custom Search and a language model.

        This method involves several steps:
        1. Parsing the input statement and preparing it for processing.
        2. Initializing a custom search tool with Google search capabilities.
        3. Defining a prompt template for the language model.
        4. Initializing a memory buffer to store conversation history.
        5. Configuring and running an agent that uses the search tool and language model to analyze the statement.
        6. Collecting and formatting the results for return or further processing.

        :param statement: The statement to be processed and contextualized.
        :param date: The date associated with the statement, if available.
        :return: A dictionary containing processed information, including search results and analysis from the language model.
        """

        google_search_tool = InformationRetrieval(cse_id=GOOGLE_CSE_ID,
                                                  api_key=GOOGLE_APIKEY,
                                                  excluded_sites=excluded_sites,
                                                  num_results=10)

        google_private = Tool(
            name='Google',
            func=google_search_tool.search,
            description=google_description,
        )

        prompt = get_prompt(date, originator)

        try:
            tools = [google_private]
            agent = create_react_agent(self.llm,
                                       tools,
                                       prompt,
                                       tools_renderer=render_text_description)
            agent_executor = AgentExecutor(agent=agent,
                                           tools=tools,
                                           verbose=False,
                                           return_intermediate_steps=True,
                                           max_iterations=5)
            agent_executor_input = {"statement": statement}
            if date:
                agent_executor_input["date"] = date
            start_time = time.time()
            result = await agent_executor.ainvoke(agent_executor_input)
            final_answer = result["output"]

            # Get the link mapping from the search tool
            link_mapping = google_search_tool.get_link_mapping()

            # Split the answer into sections
            sections = final_answer.split("Sources:")
            if len(sections) == 2:
                main_content, sources_section = sections
                if len(sources_section) > 10:
                    # Find all referenced numbers in the entire text
                    import re
                    all_refs = set(int(num) for num in re.findall(r'\[(\d+)\]', final_answer))

                    # Create new mapping with sequential numbers
                    new_mapping = {}
                    old_to_new = {}
                    new_index = 1

                    # First pass: create mapping for used references only
                    for old_num in sorted(all_refs):
                        if old_num in link_mapping:
                            old_to_new[old_num] = new_index
                            new_mapping[new_index] = link_mapping[old_num]
                            new_index += 1

                    # Replace numbers in main content
                    for old_num, new_num in old_to_new.items():
                        main_content = main_content.replace(f'[{old_num}]', f'[{new_num}]')
                        sources_section = sources_section.replace(f'[{old_num}]',
                                                                  f'[{new_num}]({new_mapping[new_num]})')

                    # Reconstruct the final answer
                    final_answer = main_content + "Sources:" + sources_section

                    # Update link_mapping to only include used references with new numbers
                    link_mapping = new_mapping
                else:
                    final_answer = "No relevant information found."

            logging.info(f"contextualizer took {time.time() - start_time} seconds")

            return {
                "output": final_answer,
                "all_google_results": google_search_tool.all_results,
                "all_queries": google_search_tool.all_queries,
                "retrieved_links": google_search_tool.retrieved_links,
                "retrieved_texts": google_search_tool.retrieved_texts,
                # "link_mapping": link_mapping,  # Add the link mapping to the output
                "status": "success"
            }

        except Exception as e:
            logging.error(f"Failed Parsing: {statement} - {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
