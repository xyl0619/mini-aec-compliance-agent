"""Backward-compatible interactive regulation retrieval entry point."""

import json

from mini_aec_agent.config import get_settings
from mini_aec_agent.regulations.retriever import RegulationRetriever, tokenize


def retrieve_chunks(query, top_k=5):
    retriever = RegulationRetriever(get_settings().regulation_index_file)
    return retriever.retrieve(query, top_k)["results"]


def print_results(query, results):
    print(
        json.dumps({"query": query, "results": results}, indent=2, ensure_ascii=False)
    )


def main() -> int:
    query = input("Enter regulation query: ").strip()
    if not query:
        print("Query cannot be empty.")
        return 2
    print_results(query, retrieve_chunks(query))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["RegulationRetriever", "retrieve_chunks", "tokenize"]
