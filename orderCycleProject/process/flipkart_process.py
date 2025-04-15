import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime
import io

def extract_text_with_fitz(input_pdf, page_num):
    doc = fitz.open(input_pdf)

    # Extract text from each page
    page = doc[page_num]
    text = page.get_text("text")
    order_id_match = re.search(r"E-Kart Logistics\s*\n*(OD\d+)", text)
    match = re.search(r"SKU(.*?)Invoice", text, re.DOTALL)
    if match:
      lines = match.group(1).split("\n")

      # Remove unwanted values
      filtered_lines = lines[:4]
      
      keys = filtered_lines[:2]
      values = filtered_lines[2:]
      
      value_chunks = [values[i:i+2] for i in range(0, len(values), 2)]

      # Create a dictionary
      data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
      data_dict["Order No."] = [order_id_match.group(1)]
      return data_dict
    else:
      return {}

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        if filtered_df.empty:
          return {}
        text = filtered_df.iloc[(0,0)]
        # Split the text by newline
        lines = text.split("\n")

        # Remove unwanted values
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        
        #place the key value in the proper position
        if filtered_lines[4] != "Order No.":
          filtered_lines.insert(4, "Order No.")
        order_matching_pos = [i for i, item in enumerate(filtered_lines) if digit_match.search(item)]
        if order_matching_pos:
          match_index = order_matching_pos[0]  # Get first match

          if match_index != 9:  # If not already at position 10
              value = filtered_lines.pop(match_index)  # Remove it
              if len(filtered_lines) < 10:  # Ensure the list has enough length
                  filtered_lines.extend([""] * (10 - len(filtered_lines)))  # Fill with empty values if needed
              if "free size" in filtered_lines[5].lower():
                  filtered_lines[5] = filtered_lines[5].split("Free Size")[0].strip()
                  filtered_lines.insert(6, "Free Size")
                  filtered_lines.pop()
                  filtered_lines[9] = value  # Insert at position 10          
        keys = filtered_lines[:5]
        values = filtered_lines[5:]
        
        value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]

        # Create a dictionary
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        return data_dict 
    else:
      return {} 


def split_pdf_custom(input_pdf, output_folder, final_output_dict, top_ratio=0.4):
    """
    Splits a PDF page into two parts based on a custom split ratio.
    Then resizes the first page of the resulting PDF to 4x6 inches, filling the entire page.
    
    :param input_pdf: Path to the input PDF file
    :param top_ratio: Fraction of the page height for the top part (default is 40%)
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Create a temporary directory for processing
    temp_dir = os.path.join(output_folder, "_temp")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    doc = fitz.open(input_pdf)  # Open the input PDF
    order_pages = {}

    for page_num, page in enumerate(doc):
        # Extract text and order information
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            if not result_dict.get("Order No.", None):
                result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)
            
        if result_dict.get("Order No.", None):
            # Create a new PDF document (split like in original code)
            new_doc = fitz.open()
            page = doc[page_num]
            rect = page.rect
            top_height = rect.height * top_ratio
            bottom_height = rect.height+1 - top_height

            # Create top part (original splitting logic)
            top_rect = fitz.Rect(0, 0, rect.width, top_height-3)
            top_page = new_doc.new_page(width=rect.width, height=top_height)
            top_page.show_pdf_page(top_page.rect, doc, page_num, clip=top_rect)

            # Create bottom part (original splitting logic)
            bottom_rect = fitz.Rect(0, top_height, rect.width, rect.height)
            bottom_page = new_doc.new_page(width=rect.width, height=bottom_height)
            bottom_page.show_pdf_page(bottom_page.rect, doc, page_num, clip=bottom_rect)

            # Save the split PDF with original page sizes
            df = pd.DataFrame(result_dict)
            orderid_name = "_".join(set([i.split("_")[0] for i in result_dict.get("Order No.", [])]))
            split_pdf_path = os.path.join(temp_dir, f"split_{orderid_name}.pdf")
            new_doc.save(split_pdf_path)
            new_doc.close()
            
            # Now convert the first page to 4x6 inches WITHOUT white margins
            # Open the split PDF
            split_doc = fitz.open(split_pdf_path)
            
            if len(split_doc) > 0:
                # Create a new document for the 4x6 first page
                first_doc = fitz.open()
                
                # Define 4x6 inch dimensions (in points)
                target_width = 4 * 72
                target_height = 6 * 72
                
                # Create the 4x6 inch page
                first_page = first_doc.new_page(width=target_width, height=target_height)
                
                # Convert the first page of the split PDF to an image with higher resolution
                page0 = split_doc[0]
                
                # Use a higher resolution for better quality
                zoom_factor = 3  # Higher zoom for better quality
                pix = page0.get_pixmap(matrix=fitz.Matrix(zoom_factor, zoom_factor))
                img_path = os.path.join(temp_dir, f"_temp_{orderid_name}_first.png")
                pix.save(img_path)
                
                from PIL import Image

                # Convert page to image at high zoom
                zoom_factor = 3
                pix = page0.get_pixmap(matrix=fitz.Matrix(zoom_factor, zoom_factor))
                img_bytes = pix.tobytes("png")

                # Load into Pillow and resize
                with Image.open(io.BytesIO(img_bytes)) as img:
                    resized_img = img.resize((288, 432), Image.Resampling.LANCZOS)  # 4x6 inches at 72 dpi
                    img_path = os.path.join(temp_dir, f"_temp_{orderid_name}_resized.png")
                    resized_img.save(img_path)

                # Insert resized image into 4x6 PDF page
                first_page.insert_image(
                    fitz.Rect(0, 0, target_width, target_height),  # Fill whole page
                    filename=img_path
                )
                
                first_pdf_path = os.path.join(temp_dir, f"_temp_{orderid_name}_first.pdf")
                first_doc.save(first_pdf_path)
                first_doc.close()
                
                # Clean up the image
                try:
                    os.remove(img_path)
                except:
                    pass
                
                # Now create the final document with 4x6 first page and remaining pages
                final_doc = fitz.open()
                
                # Add the 4x6 first page
                first_temp_doc = fitz.open(first_pdf_path)
                final_doc.insert_pdf(first_temp_doc)
                first_temp_doc.close()
                
                # Add all remaining pages from the split document
                for i in range(1, len(split_doc)):
                    final_doc.insert_pdf(split_doc, from_page=i, to_page=i)
                
                # Save the final document
                output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
                final_doc.save(output_pdf_path)
                final_doc.close()
                split_doc.close()
                
                # Process order information
                for i in df.to_dict(orient="records"):
                    orderid = i.get("Order No.", None)
                    if not orderid:
                        continue
                    
                    # Extract SKU and Qty information
                    sku_qty_items = [{"sku": d["SKU"], "Qty": d["Quantity"],"AWB":d["Tracking ID"]} for d in final_output_dict if d["Order Id"] == orderid]
                    
                    if not sku_qty_items:
                        sku = i.get(" ID | Description", None).split("|")[0].split(" ")[1] if i.get(" ID | Description", None) else ""
                        sku_qty_items = [{
                            "sku": sku,
                            "Qty": i.get("QTY", None),
                        }]
                    
                    # Initialize the order_pages structure
                    if str(orderid) not in order_pages:
                        order_pages[str(orderid)] = []
                        order_pages[str(orderid)].append(sku_qty_items)  # Add as a nested list
                    else:
                        # If already exists, check if we need to update the SKU/Qty list
                        if len(order_pages[str(orderid)]) > 0 and isinstance(order_pages[str(orderid)][0], list):
                            # Update existing SKU list instead of replacing
                            for item in sku_qty_items:
                                if item not in order_pages[str(orderid)][0]:
                                    order_pages[str(orderid)][0].append(item)
                        else:
                            # If structure is not as expected, initialize correctly
                            order_pages[str(orderid)] = [sku_qty_items]
                
                # Add output PDF location to order_pages
                if str(orderid) in order_pages:
                    # Check if output_pdf_location already exists
                    pdf_location_exists = False
                    for item in order_pages[str(orderid)]:
                        if isinstance(item, dict) and "output_pdf_location" in item:
                            item["output_pdf_location"] = output_pdf_path
                            pdf_location_exists = True
                            break
                    
                    if not pdf_location_exists:
                        order_pages[str(orderid)].append({"output_pdf_location": output_pdf_path})
            
        else:
            # Handle pages without order information (if output_pdf_path exists)
            if 'output_pdf_path' in locals() and os.path.exists(output_pdf_path):
                new_doc = fitz.open(output_pdf_path)
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                new_doc.insert_page(-1) 
                output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
                new_doc.save(output_pdf_path_temp)
                new_doc.close()
                os.remove(output_pdf_path)
                os.rename(output_pdf_path_temp, output_pdf_path)
    
    # Clean up temporary files
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
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter=',')
    return df
  
def grab_required_fields(data):
    required_columns = ["Order Id", "SKU", "Quantity","Tracking ID"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data
  

