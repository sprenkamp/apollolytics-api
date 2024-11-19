import os
from langchain.agents import create_react_agent, AgentExecutor
from langchain.agents import Tool
from langchain import hub
from googleapiclient.discovery import build
import re
import pandas as pd
from dotenv import load_dotenv
import logging
import time

from langchain_core.tools import BaseTool
from llm.load_llm import load_llm

# Load environment variables, including API keys for Google and OpenAI.
load_dotenv()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "default_cse_id")
GOOGLE_APIKEY = os.getenv("GOOGLE_API_KEY", "default_api_key")

# Load excluded URLs from a CSV file
fake = pd.read_csv("llm/ressources/mediabiasfactcheck_fakenews.csv")
fake = fake[fake["Traffic/Popularity"] != "Minimal Traffic"]
urls = fake["source_link"].apply(lambda x: x.split("//")[-1].split("www.")[-1].split("/")[0])


def build_query(query, excluded_sites):
    exclusion_query = ' '.join([f'-site:{site}' for site in excluded_sites])
    return f'{query} {exclusion_query}'


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
        description = f"{tool.name} - {tool.description}"
        descriptions.append(description)
    return "\n".join(descriptions)


class InformationRetrieval:
    def __init__(self, cse_id, api_key, num_results=10):
        self.cse_id = cse_id
        self.api_key = api_key
        self.num_results = num_results
        self.start = 0
        self.last_request = ""
        self.all_results = {}
        self.all_queries = []
        self.retrieved_links = []
        self.retrieved_texts = []

    def format_google(self, google_res):
        max_link_length = 100
        formatted_res = []
        for idx, res in enumerate(google_res):
            link = res.get("link", "")
            link_len = len(link)
            if link_len > max_link_length:
                print(f"Attention: Link length of {link_len} exceeds maximum of {max_link_length} characters.")
                link = link[:max_link_length] + "..."
            title = res.get("title", "")
            snippet = res.get("snippet", "")
            metatags = res.get("pagemap", {}).get("metatags", [{}])
            published_time = metatags[0].get("article:published_time", None)

            if published_time:
                published_time = published_time.split("T")[0]
                try:
                    published_time = pd.to_datetime(published_time).strftime('%Y-%b')
                except:
                    published_time = "NO DATE"

            title = re.sub('\.+', '.', title)
            title = re.sub(' +', ' ', title)
            snippet = re.sub('\.+', '.', snippet)
            snippet = re.sub(' +', ' ', snippet)

            formatted_entry = f"{0 + idx + 1}. {link} ({published_time}): {title}. {snippet}.\n"
            formatted_res.append(formatted_entry)

        return "".join(formatted_res)

    def search(self, query):
        try:
            for i in range(3):
                if self.last_request != query:
                    self.start = 0
                    self.all_queries.append(query)
                    self.last_request = query

                service = build("customsearch", "v1", developerKey=self.api_key)
                response = service.cse().list(q=build_query(query, excluded_sites=urls), cx=self.cse_id,
                                              num=self.num_results, start=self.start).execute()
                results = response['items']

                self.start += len(results)
                if query in self.all_results:
                    self.all_results[query] += results
                else:
                    self.all_results[query] = results

            return self.format_google(self.all_results[query])
        except Exception as e:
            print(e)
            return ""


google_description = """Get previews of the top google search results to get more information about the statement. The function always returns the next 10 results and can be called multiple times. If initial results seem unrelated you may use quotation marks to search for an exact phrase. Use a minus sign to exclude a word from the search.  Use before:date and after:date to search for results within a specific time period. Do not google the entire statement verbatim."""


def get_prompt(date, originator):
    prompt = hub.pull("hwchase17/react")

    prompt_template = """You are an Assistant tasked to contextualise potentially misleading statements to make sure users are safe and well informed. You have access to the following tools:\n{tools}\nDo not use any tool more than three times. Use the following format:\n\nQuestion: the input question you must answer\nThought: you should always think about what to do\nAction: the action to take, should be one of [{tool_names}]\nAction Input: the input to the action\nObservation: the result of the action\n... (this Thought/Action/Action Input/Observation can repeat 3 times)\nThought: I now have sufficient information to provide context for the user.\nFinal Answer: The context demanded by the user.\n\n
        **Final Response Format:**
        - **Facts:** (Simplified, factual summary with sources)
        - **Misinformation Explanation:** (Detailed reasoning)
        - **Warning:** (Specific risks of misinformation)
        - **Sources:** (List all important sources with hyperlinks)
    
        **Example Final Answer:**
        Facts: Electric vehicles are generally less harmful to the environment over their lifetime than gasoline cars, though they do have a high environmental cost at the production stage.
        Warn: Misleading statements may ignore the full lifecycle impacts.
        Explain: Comparing only the production impacts oversimplifies the broader environmental considerations.
        Sources: 
        - [EPA](https://www.epa.gov/greenvehicles/electric-vehicle-myths)
        - [MIT Climate Portal](https://climate.mit.edu/ask-mit/are-electric-vehicles-definitely-better-climate-gas-powered-cars)
        - [NY Post](https://nypost.com/2024/03/05/business/evs-release-more-toxic-emissions-are-worse-for-the-environment-study/)
        \nBegin!\n\nQuestion: Contextualise the statement: '{statement}'{originator_section}{date_section}\nThought:{agent_scratchpad}"""

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
                            max_tokens=2000,
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

        google_search_tool = InformationRetrieval(cse_id=GOOGLE_CSE_ID, api_key=GOOGLE_APIKEY, num_results=10)

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
            final_answer = await agent_executor.ainvoke(agent_executor_input)
            logging.info(f"contextualizer took {time.time() - start_time} seconds")

            return {
                "output": final_answer,
                "all_google_results": google_search_tool.all_results,
                "all_queries": google_search_tool.all_queries,
                "retrieved_links": google_search_tool.retrieved_links,
                "retrieved_texts": google_search_tool.retrieved_texts,
                "status": "success"
            }

        except Exception as e:
            logging.error(f"Failed Parsing: {statement} - {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
