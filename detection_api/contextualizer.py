import os
from langchain.agents import create_react_agent, AgentExecutor
from langchain.agents import Tool
from langchain import hub
from googleapiclient.discovery import build
import re
import pandas as pd
from dotenv import load_dotenv
import logging

from load_llm import load_llm  # Custom function for loading language models
from tqdm import tqdm

# Load environment variables, including API keys for Google and OpenAI.
load_dotenv()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "default_cse_id")
GOOGLE_APIKEY = os.getenv("GOOGLE_API_KEY", "default_api_key")

# Load excluded URLs from a CSV file
fake = pd.read_csv("mediabiasfactcheck_fakenews.csv")
fake = fake[fake["Traffic/Popularity"] != "Minimal Traffic"]
urls = fake["source_link"].apply(lambda x: x.split("//")[-1].split("www.")[-1].split("/")[0])


def build_query(query, excluded_sites):
    exclusion_query = ' '.join([f'-site:{site}' for site in excluded_sites])
    return f'{query} {exclusion_query}'


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
            num_tokens = 0

            agent = create_react_agent(self.llm, tools, prompt)
            agent_executor = AgentExecutor(agent=agent,
                                           tools=tools,
                                           verbose=True,
                                           return_intermediate_steps=True,
                                           max_iterations=5)
            agent_executor_input = {"statement": statement}
            if date:
                agent_executor_input["date"] = date

            for chunk in agent_executor.stream(agent_executor_input):
                content = chunk["messages"][0].dict()["content"]
                print(content)
                num_tokens += len(content)
                if "output" in chunk:
                    final_answer = chunk["output"]
            print(f"APPROXIMATE cost: {num_tokens * 0.5 / 10 ** 4:.4f} Cent(s)")

            return {
                "output": final_answer,
                "all_google_results": google_search_tool.all_results,
                "all_queries": google_search_tool.all_queries,
                "retrieved_links": google_search_tool.retrieved_links,
                "retrieved_texts": google_search_tool.retrieved_texts,
            }

        except Exception as e:
            logging.error(f"Failed Parsing: {statement} - {str(e)}")
            return {"output": "Failed to process the statement."}


if __name__ == "__main__":
    contextualizer = Contextualizer(
        cse_id=GOOGLE_CSE_ID,
        api_key=GOOGLE_APIKEY,
        model_name="gpt-3.5-turbo")
    text = """Tucker Carlson: So, that was eight years before the current conflict started. What was the trigger for you? What was the moment where you decided you had to do this? 

Vladimir Putin: Initially, it was the coup in Ukraine that provoked the conflict.

By the way, back then the representatives of three European countries – Germany, Poland and France – arrived. They were the guarantors of the signed agreement between the Government of Yanukovych and the opposition. They signed it as guarantors. Despite that, the opposition staged a coup and all these countries pretended that they didn’t remember that they were guarantors of a peaceful settlement. They just threw it in the stove right away and nobody recalls that.

I don’t know if the US know anything about that agreement between the opposition and the authorities and its three guarantors who, instead of bringing this whole situation back in the political field, supported the coup. Although, it was meaningless, believe me. Because President Yanukovych agreed to all conditions, he was ready to hold early election which he had no chance to win, frankly speaking. Everyone knew that.

But then why the coup, why the victims? Why threaten Crimea? Why launch an operation in Donbass? This I do not understand. That is exactly what the miscalculation is. The CIA did its job to complete the coup. I think one of the Deputy Secretaries of State said that it cost a large sum of money, almost 5 billion dollars. But the political mistake was colossal! Why would they have to do that? All this could have been done legally, without victims, without military action, without losing Crimea. We would have never considered to even lift a finger if it hadn’t been for the bloody developments on Maidan.

Because we agreed with the fact that after the collapse of the Soviet Union our borders should be along the borders of former Union’s republics. We agreed to that. But we never agreed to NATO’s expansion and moreover we never agreed that Ukraine would be in NATO. We did not agree to NATO bases there without any discussion with us. For decades we kept urging them: don’t do this, don’t do that.

And what triggered the latest events? Firstly, the current Ukrainian leadership declared that it would not implement the Minsk agreements, which had been signed, as you know, after the events of 2014, in Minsk, where the plan of a peaceful settlement in Donbass was set forth. But no, the current Ukrainian leadership, foreign minister, all other officials and then President himself said that they don’t like anything about the Minsk agreements. In other words, they were not going to implement them. A year or a year and a half ago, former leaders of Germany and France said openly to the whole world that they indeed signed the Minsk agreements but they never intended to implement them. They simply led us by the nose.

Tucker Carlson: Was there anyone free to talk to? Did you call the US President, Secretary of State and say if you keep militarizing Ukraine with NATO forces, we are going to act?

Vladimir Putin: We talked about this all the time. We addressed the United States’ and European countries’ leadership to stop these developments immediately, to implement the Minsk agreements. Frankly speaking, I didn’t know how we were going to do this but I was ready to implement them. These agreements were complicated for Ukraine; they included lots of elements of those Donbass territories’ independence. That’s true. However, I was absolutely confident, and I am saying this to you now: I honestly believed that if we managed to convince the residents of Donbass – and we had to work hard to convince them to return to the Ukrainian statehood – then gradually the wounds would start to heal. When this part of territory reintegrated itself into common economic, social environment, when the pensions and social benefits were paid again, all the pieces would gradually fall into place. 

No, nobody wanted that, everybody wanted to resolve the issue by military force only. But we could not let that happen.

And the situation got to the point, when the Ukrainian side announced: “No, we will not implement anything.” They also started preparing for military action. It was they who started the war in 2014. Our goal is to stop this war. And we did not start this war in 2022. This is an attempt to stop it. 

Tucker Carlson: Do you think you have stopped it now? I mean have you achieved your aims? 

Vladimir Putin: No, we haven't achieved our aims yet, because one of them is denazification. This means the prohibition of all kinds of neo-Nazi movements. This is one of the problems that we discussed during the negotiation process, which ended in Istanbul early last year, and it was not our initiative, because we were told (by the Europeans, in particular) that “it was necessary to create conditions for the final signing of the documents.” My counterparts in France and Germany said, “How can you imagine them signing a treaty with a gun to their heads? The troops should be pulled back from Kiev.” I said, “All right.” We withdrew the troops from Kiev. 

As soon as we pulled back our troops from Kiev, our Ukrainian negotiators immediately threw all our agreements reached in Istanbul into the bin and got prepared for a longstanding armed confrontation with the help of the United States and its satellites in Europe. That is how the situation has developed. And that is how it looks now. 

Tucker Carlson: What is denazification? What would that mean? 

Vladimir Putin: That is what I want to talk about right now. It is a very important issue. 

Denazification. After gaining independence, Ukraine began to search, as some Western analysts say, its identity. And it came up with nothing better than to build this identity upon some false heroes who collaborated with Hitler. 

I have already said that in the early 19th century, when the theorists of independence and sovereignty of Ukraine appeared, they assumed that an independent Ukraine should have very good relations with Russia. But due to the historical development, these territories were part of the Polish-Lithuanian Commonwealth – Poland, where Ukrainians were persecuted and treated quite brutally and were subjected to cruel behaviour. There were also attempts to destroy their identity. All this remained in the memory of the people. When World War II broke out, part of this extremely nationalist elite collaborated with Hitler, believing that he would bring them freedom. The German troops, even the SS troops made Hitler's collaborators do the dirtiest work of exterminating the Polish and Jewish population. Hence this brutal massacre of the Polish and Jewish population as well as the Russian population too. This was led by the persons who are well known – Bandera, Shukhevich. It was these people who were made national heroes – that is the problem. And we are constantly told that nationalism and neo-Nazism exist in other countries as well. Yes, there are seedlings, but we uproot them, and other countries fight against them. But Ukraine is not the case. These people have been turned into national heroes in Ukraine. Monuments to these people have been erected, they are displayed on flags, their names are shouted by crowds that walk with torches, as it was in Nazi Germany. These were the people who exterminated Poles, Jews and Russians. It is necessary to stop this practice and prevent the dissemination of this concept.

I say that Ukrainians are part of the one Russian people. They say, “No, we are a separate people.” Okay, fine. If they consider themselves a separate people, they have the right to do so, but not on the basis of Nazism, the Nazi ideology. 

Tucker Carlson: Would you be satisfied with the territory that you have now?

Vladimir Putin: I will finish answering the question. You just asked a question about neo-Nazism and denazification. 

Look, the President of Ukraine visited Canada. This story is well known but is silenced in the Western countries: The Canadian parliament introduced a man who, as the speaker of the parliament said, fought against the Russians during World War II. Well, who fought against the Russians during World War II? Hitler and his accomplices. It turned out that this man served in the SS troops. He personally killed Russians, Poles, and Jews. The SS troops consisted of Ukrainian nationalists who did this dirty work. The President of Ukraine stood up with the entire Parliament of Canada and applauded this man. How can this be imagined? The President of Ukraine himself, by the way, is a Jew by nationality."""

    result = contextualizer.identify_seemingly_factual(text)
    print(f"Found {len(result)} seemingly factual statements in the text.")

    answer = {}
    for statement in tqdm(result):
        process_statement = contextualizer.process_statement(statement)
        answer[statement] = process_statement["output"]

        print("--------------------")
        print(statement)
        print(answer[statement])
        print("--------------------")
