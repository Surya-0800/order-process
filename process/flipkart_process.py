import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime
import io
from PIL import Image, ImageChops

def extract_text_with_fitz(input_pdf, page_num):
    doc = fitz.open(input_pdf)
    page = doc[page_num]
    text = page.get_text("text")
    order_id_match = re.search(r"E-Kart Logistics\s*\n*(OD\d+)", text)
    match = re.search(r"SKU(.*?)Invoice", text, re.DOTALL)
    if match:
        lines = match.group(1).split("\n")
        filtered_lines = lines[:4]
        keys = filtered_lines[:2]
        values = filtered_lines[2:]
        value_chunks = [values[i:i+2] for i in range(0, len(values), 2)]
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        data_dict["Order No."] = [order_id_match.group(1)]
        return data_dict
    else:
        return {}

def extract_text_with_camelot(pdf_path, page_number):
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        if filtered_df.empty:
            return {}
        text = filtered_df.iloc[(0,0)]
        lines = text.split("\n")
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        if filtered_lines[4] != "Order No.":
            filtered_lines.insert(4, "Order No.")
        order_matching_pos = [i for i, item in enumerate(filtered_lines) if digit_match.search(item)]
        if order_matching_pos:
            match_index = order_matching_pos[0]
            if match_index != 9:
                value = filtered_lines.pop(match_index)
                if len(filtered_lines) < 10:
                    filtered_lines.extend([""] * (10 - len(filtered_lines)))
                if "free size" in filtered_lines[5].lower():
                    filtered_lines[5] = filtered_lines[5].split("Free Size")[0].strip()
                    filtered_lines.insert(6, "Free Size")
                    filtered_lines.pop()
                    filtered_lines[9] = value
        keys = filtered_lines[:5]
        values = filtered_lines[5:]
        value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        return data_dict
    else:
        return {}

def split_pdf_custom(input_pdf, output_folder, final_output_dict, top_ratio=0.46):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    temp_dir = os.path.join(output_folder, "_temp")
    os.makedirs(temp_dir, exist_ok=True)
    doc = fitz.open(input_pdf)
    order_pages = {}

    for page_num, page in enumerate(doc):
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            if not result_dict.get("Order No."):
                result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)

        if result_dict.get("Order No."):
            new_doc = fitz.open()
            page = doc[page_num]
            rect = page.rect
            top_height = rect.height * top_ratio
            bottom_height = rect.height + 1 - top_height
            top_rect = fitz.Rect(0, 0, rect.width, top_height - 3)
            top_page = new_doc.new_page(width=rect.width, height=top_height)
            top_page.show_pdf_page(top_page.rect, doc, page_num, clip=top_rect)
            bottom_rect = fitz.Rect(0, top_height, rect.width, rect.height)
            bottom_page = new_doc.new_page(width=rect.width, height=bottom_height)
            bottom_page.show_pdf_page(bottom_page.rect, doc, page_num, clip=bottom_rect)
            df = pd.DataFrame(result_dict)
            orderid_name = "_".join(set([i.split("_")[0] for i in result_dict.get("Order No.", [])]))
            split_pdf_path = os.path.join(temp_dir, f"split_{orderid_name}.pdf")
            new_doc.save(split_pdf_path)
            new_doc.close()

            # Create the final output PDF directly from the split PDF
            final_doc = fitz.open()
            split_doc = fitz.open(split_pdf_path)
            
            # Simply include all pages from the split document without 4x6 conversion
            for i in range(len(split_doc)):
                final_doc.insert_pdf(split_doc, from_page=i, to_page=i)
                
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
            final_doc.save(output_pdf_path)
            final_doc.close()
            split_doc.close()

            for i in df.to_dict(orient="records"):
                orderid = i.get("Order No.")
                if not orderid:
                    continue
                sku_qty_items = [{"sku": d["SKU"], "Qty": d["Quantity"], "AWB": d["Tracking ID"]} for d in final_output_dict if d["Order Id"] == orderid]
                if not sku_qty_items:
                    sku = i.get(" ID | Description", "").split("|")[0].split(" ")[1] if i.get(" ID | Description") else ""
                    sku_qty_items = [{"sku": sku, "Qty": i.get("QTY")}]  
                if str(orderid) not in order_pages:
                    order_pages[str(orderid)] = [sku_qty_items]
                else:
                    if isinstance(order_pages[str(orderid)][0], list):
                        for item in sku_qty_items:
                            if item not in order_pages[str(orderid)][0]:
                                order_pages[str(orderid)][0].append(item)
                    else:
                        order_pages[str(orderid)] = [sku_qty_items]
            if str(orderid) in order_pages:
                if not any(isinstance(i, dict) and "output_pdf_location" in i for i in order_pages[str(orderid)]):
                    order_pages[str(orderid)].append({"output_pdf_location": output_pdf_path})
        else:
            if 'output_pdf_path' in locals() and os.path.exists(output_pdf_path):
                new_doc = fitz.open(output_pdf_path)
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                new_doc.insert_page(-1)
                output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
                new_doc.save(output_pdf_path_temp)
                new_doc.close()
                os.remove(output_pdf_path)
                os.rename(output_pdf_path_temp, output_pdf_path)

    if os.path.exists(temp_dir):
        for temp_file in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, temp_file))
            except:
                pass
        try:
            os.rmdir(temp_dir)
        except:
            pass

    return order_pages

def csv_to_dataframe(file_path):
    df = pd.read_csv(file_path, delimiter=',')
    return df

def grab_required_fields(data):
    required_columns = ["Order Id", "SKU", "Quantity", "Tracking ID"]
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data