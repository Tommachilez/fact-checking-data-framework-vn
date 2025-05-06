# data_handler.py
# -*- coding: utf-8 -*-

"""
Functions for handling data input (reading queries) and potentially output (JSONL writing).
"""

import logging
import json
from typing import List, Optional, Dict, TextIO

import pandas as pd
from datasets import load_dataset, concatenate_datasets

def read_queries_from_vifactcheck(column_name: str) -> Optional[List[str]]:
    """
    Reads a specified column from a CSV or Excel file into a list of unique queries.

    Args:
        file_path: Path to the input dataset file (CSV or Excel).
        column_name: Name of the column containing search queries.

    Returns:
        A list of unique, non-empty queries as strings, or None if an error occurs.
    """
    logging.info("Reading queries from column '%s'.", column_name)
    try:
        ds = load_dataset("tranthaihoa/vifactcheck")
        combined = concatenate_datasets([ds['train'], ds['dev'], ds['test']])
        df = combined.to_pandas()

        if column_name not in df.columns:
            logging.error("Query column '%s' not found. Available columns: %s",
                          column_name, df.columns.tolist())
            return None # Indicate column not found error

        # Get unique, non-null queries, convert to string just in case
        queries = df[column_name].dropna().astype(str).unique().tolist()

        # Filter out potentially empty strings after conversion
        queries = [q for q in queries if q.strip()]

        logging.info("Read %d unique, non-empty queries from column '%s'.", len(queries), column_name)
        if not queries:
            logging.warning("No valid, non-empty queries found in the specified column.")
            # Return empty list instead of None if no queries found but file/column were ok
            return []
        return queries

    except Exception as e:
        logging.error("Error reading input: %s", e, exc_info=True)
        return None # Indicate other reading error


def save_jsonl_record(outfile: TextIO, record: Dict) -> bool:
    """
    Safely serializes a dictionary and writes it as a line to an open JSONL file handle.

    Args:
        outfile: An open text file handle in write/append mode with UTF-8 encoding.
        record: The dictionary to write.

    Returns:
        True if writing was successful, False otherwise.
    """
    try:
        # ensure_ascii=False is important for non-English characters
        json_line = json.dumps(record, ensure_ascii=False)
        outfile.write(json_line + '\n')
        return True
    except Exception as e:
        # Log error but don't stop the entire process for one failed write
        logging.error("Failed to serialize/write record for URL '%s': %s", record.get('url', 'N/A'), e)
        return False
