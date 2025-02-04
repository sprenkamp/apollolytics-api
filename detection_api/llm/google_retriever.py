import logging
import re
from typing import List, Dict, Tuple

import pandas as pd
from googleapiclient.discovery import build


def build_query(query, excluded_sites):
    exclusion_query = ' '.join([f'-site:{site}' for site in excluded_sites])
    return f'{query} {exclusion_query}'


class InformationRetrieval:
    def __init__(self, cse_id: str, api_key: str, excluded_sites: List[str], num_results: int = 10):
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
        self.link_number_mapping = {}  # Maps link numbers to actual URLs
        self.current_link_number = 1  # Counter for assigning link numbers

    def get_next_link_number(self) -> int:
        """Get next available link number and increment counter."""
        number = self.current_link_number
        self.current_link_number += 1
        return number

    def format_google(self, google_res: List[Dict]) -> Tuple[str, Dict[int, str]]:
        """Format Google search results and maintain link number mapping."""
        formatted_res = []
        query_link_mapping = {}

        for res in google_res:
            link = res.get("link", "")

            title = re.sub('\.+', '.', res.get("title", ""))
            title = re.sub(' +', ' ', title)
            snippet = re.sub('\.+', '.', res.get("snippet", ""))
            snippet = re.sub(' +', ' ', snippet)

            # Get publication date if available
            metatags = res.get("pagemap", {}).get("metatags", [{}])
            published_time = metatags[0].get("article:published_time", None)

            if published_time:
                published_time = published_time.split("T")[0]
                try:
                    published_time = pd.to_datetime(published_time).strftime('%Y-%b')
                except:
                    published_time = "NO DATE"

            # Assign or retrieve link number
            if link not in self.link_number_mapping.values():
                link_number = self.get_next_link_number()
                self.link_number_mapping[link_number] = link
            else:
                link_number = [k for k, v in self.link_number_mapping.items() if v == link][0]

            query_link_mapping[link_number] = link

            # Format entry with link number instead of URL
            formatted_entry = f"[{link_number}] ({published_time if published_time else 'NO DATE'}): {title}. {snippet}.\n"
            formatted_res.append(formatted_entry)

        if not formatted_res:
            logging.warning("No relevant information found.")
            return "No relevant information found.", {}

        return "".join(formatted_res), query_link_mapping

    def search(self, query: str) -> str:
        """Perform Google search and return formatted results with numbered references."""
        try:
            if self.last_request != query:
                self.start = 0
                self.all_queries.append(query)
                self.last_request = query

            service = build("customsearch", "v1", developerKey=self.api_key)

            for _ in range(3):  # Make up to 3 requests
                response = service.cse().list(
                    q=build_query(query, self.excluded_sites),
                    cx=self.cse_id,
                    num=self.num_results,
                    start=self.start
                ).execute()

                results = response['items']
                self.start += len(results)

                if query in self.all_results:
                    self.all_results[query].extend(results)
                else:
                    self.all_results[query] = results

            formatted_results, query_mapping = self.format_google(self.all_results[query])
            return formatted_results

        except Exception as e:
            logging.warning(f"Search error occurred: {e}", exc_info=True)
            return "No relevant information found."

    def get_link_mapping(self) -> Dict[int, str]:
        """Return the current link number to URL mapping."""
        return self.link_number_mapping
