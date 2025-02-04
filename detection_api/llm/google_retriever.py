import logging
import re

import pandas as pd
from googleapiclient.discovery import build


def build_query(query, excluded_sites):
    exclusion_query = ' '.join([f'-site:{site}' for site in excluded_sites])
    return f'{query} {exclusion_query}'


class InformationRetrieval:
    def __init__(self, cse_id, api_key, excluded_sites, num_results=10):
        self.cse_id = cse_id
        self.api_key = api_key
        self.num_results = num_results
        self.start = 0
        self.last_request = ""
        self.all_results = {}
        self.all_queries = []
        self.retrieved_links = []
        self.retrieved_texts = []
        self.excluded_sites = excluded_sites

    def format_google(self, google_res):
        max_link_length = 1000
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
        if len(formatted_res) == 0:
            logging.warning("No relevant information found.")
            return "No relevant information found."
        return "".join(formatted_res)

    def search(self, query):
        try:
            for i in range(3):
                if self.last_request != query:
                    self.start = 0
                    self.all_queries.append(query)
                    self.last_request = query

                service = build("customsearch", "v1", developerKey=self.api_key)
                response = service.cse().list(q=build_query(query, excluded_sites=self.excluded_sites), cx=self.cse_id,
                                              num=self.num_results, start=self.start).execute()
                results = response['items']

                self.start += len(results)
                if query in self.all_results:
                    self.all_results[query] += results
                else:
                    self.all_results[query] = results

            return self.format_google(self.all_results[query])
        except Exception as e:
            logging.warning(f"Some error occurred during the search. Error: {e}", exc_info=True)
            return "No relevant information found."
