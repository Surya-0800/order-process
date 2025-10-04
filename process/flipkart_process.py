import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime
import numpy as np
# from pydash import clean as _c
from ordercycle.models import OrderPDF
from .db_utils import save_pdf_to_database

def extract_text_with_fitz(input_pdf, page_num, only_orderid=False):
    doc = fitz.open(input_pdf)

    # Extract text from each page
    if only_orderid:
      page = doc[page_num-1]
    else:
      page = doc[page_num]
    text = page.get_text("text")
    order_id_match = re.search(r"(?:E-Kart Logistics|Order Id:)\s*(?:\\n)?\n*(OD\d+)", text)
    awb = re.search(r"AWB No\. (\w+)", text.replace("\n", " "))
    if only_orderid:
      return order_id_match.group(1),awb.group(1)
    match = re.search(r"SKU(.*?)Invoice", text, re.DOTALL)
    if match:
      lines = match.group(1).split("\n")
      # lines = re.sub(r'FMPC.*', '', match.group(1), flags=re.DOTALL)

      # Remove unwanted values
      filtered_lines = lines[:4]
      
      keys = filtered_lines[:2]
      values = filtered_lines[2:]
      
      value_chunks = [values[i:i+2] for i in range(0, len(values), 2)]

      # Create a dictionary
      data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
      data_dict["Order No."] = [order_id_match.group(1)]

      # total_len = len(data_dict["SKU"])
      awb_value = awb.group(1) if awb else ''
      data_dict["AWB"] = [awb_value]
      #check if qty is a digit
      if not re.search(r"^\d+$", data_dict["QTY"][0]):
        return {}
      return data_dict
    else:
      return {}

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number), flavor="lattice")
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        df = tables[0].df
        # Find indices of rows where any cell contains "SKU"
        sku_indices = df.index[
            df.apply(lambda row: row.astype(str).str.contains("SKU", case=False, na=False).any(), axis=1)
        ].tolist()

        # Include the next row index as well (if within bounds)
        extended_indices = sku_indices + [i + 1 for i in sku_indices if i + 1 < len(df)]

        # Drop duplicates and sort to maintain order
        extended_indices = sorted(set(extended_indices))

        # Extract those rows
        filtered_df = df.loc[extended_indices].reset_index(drop=True)
        if filtered_df.empty:
          return {}
        filtered_df = filtered_df.replace(r'^\s*$', np.nan, regex=True).infer_objects(copy=False)
        filtered_df = filtered_df.where(pd.notnull(filtered_df), np.nan)
        filtered_df.dropna(how='all', inplace=True)  
        filtered_df.dropna(axis=1, how='all', inplace=True)
        filtered_df.reset_index(drop=True, inplace=True)
        filtered_df.columns = filtered_df.iloc[0]
        filtered_df = filtered_df[1:]
        if str(filtered_df["QTY"][1]) == "nan":
          filtered_df.at[1, 'QTY'] = filtered_df.at[1, 'SKU ID | Description'].split(" ")[-1]
        order_id, awb = extract_text_with_fitz(pdf_path, page_number, only_orderid=True)
        filtered_df.loc[:, 'Order No.'] = [order_id]
        filtered_df.loc[:, 'AWB'] = [awb]
        filtered_df = filtered_df.rename(columns={'SKU ID | Description': ' ID | Description'})
        return filtered_df.to_dict(orient='list')
    else:
      return {} 


def split_pdf_custom(input_pdf, output_folder, final_output_dict, top_ratio=0.46):
    """
    Splits a PDF page into two parts based on a custom split ratio.
    
    :param input_pdf: Path to the input PDF file
    :param top_ratio: Fraction of the page height for the top part (default is 40%)
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    doc = fitz.open(input_pdf)  # Open the input PDF
    
    order_pages = {}
    saved_orders = []

    for page_num, page in enumerate(doc):
        
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            if not result_dict.get("Order No.", None):
              result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        if result_dict.get("Order No.", None):
            new_doc = fitz.open()  # Create a new PDF document
            page = doc[page_num]  # Get current page
            rect = page.rect  # Get original page size
            top_height = rect.height * top_ratio  # Calculate top section height
            bottom_height = rect.height +1 - top_height  # Remaining height for the bottom section

            side_margin = 190
            top_margin = 27  

            top_rect = fitz.Rect(side_margin, top_margin, rect.width - side_margin, top_height - 3)

            cropped_width = rect.width - (2 * side_margin)  # New width without margins
            # Adjust the height to account for the top margin
            cropped_height = top_height - top_margin
            top_page = new_doc.new_page(width=cropped_width, height=cropped_height)
            top_page.show_pdf_page(top_page.rect, doc, page_num, clip=top_rect)

            # --- Create Bottom Part (Custom Height) ---
            bottom_rect = fitz.Rect(0, top_height, rect.width, rect.height)
            bottom_page = new_doc.new_page(width=rect.width, height=bottom_height)
            bottom_page.show_pdf_page(bottom_page.rect, doc, page_num, clip=bottom_rect)

            # Save the new PDF with two pages per original page
            df = pd.DataFrame(result_dict)
            df = df.astype(str)
            orderid_name = "_".join(set([i.split("_")[0] for i in result_dict.get("Order No.", [])]))
            for i in df.to_dict(orient="records"):
              orderid = i.get("Order No.", None)
              order_details = {orderid: [{"sku": d["SKU"], "Qty": d["Quantity"], "AWB":d["Tracking ID"]} for d in final_output_dict if d["Order Id"] == orderid]}
              if not order_details[orderid]:
                sku = re.sub(r'^\d\s*', '', i.get(" ID | Description", None).split("|")[0]) if i.get(" ID | Description", None) else ""
                order_details[orderid] = [{
                "sku" : sku.strip(),
                "Qty" : i.get("QTY", None).strip(),
                "AWB": i.get("AWB", None).strip(),
              }]
              order_pages[str(orderid)] = []
              order_pages[str(orderid)].append(order_details[orderid])
  
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
            order_pages[str(orderid)].append({"output_pdf_location" : output_pdf_path})
            new_doc.save(output_pdf_path)
            order_pdf, created = save_pdf_to_database(
                order_id=orderid,
                pdf_path=output_pdf_path,
                order_details=order_details[orderid],
                source_type="flipkart"
            )
            saved_orders.append(order_pdf)
            os.remove(output_pdf_path)
        else:
            new_doc = fitz.open(output_pdf_path)
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_doc.insert_page(-1) 
            output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
            new_doc.save(output_pdf_path_temp)
            os.remove(output_pdf_path)
            os.rename(output_pdf_path_temp, output_pdf_path)
        new_doc.close()
        
    return order_pages
  
def csv_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter=',')
    return df
  
def grab_required_fields(data):
    required_columns = ["Order Id", "SKU", "Quantity", "Tracking ID"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data
  