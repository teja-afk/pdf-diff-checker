import io
import sys
import os
from PyPDF2 import PdfReader
import difflib
from PIL import ImageChops, ImageDraw
import pymupdf

def compare_images(img1, img2):
    diff = ImageChops.difference(img1, img2)
    if diff.getbbox():
        annotated = img1.copy()
        draw = ImageDraw.Draw(annotated)
        # mark changed pixels with rectangles
        for x in range(0, img1.width, 10):
            for y in range(0, img1.height, 10):
                if diff.getpixel((x, y)) != (0, 0, 0):
                    draw.rectangle([x, y, x+5, y+5], outline="red")
        return annotated
    return None


def extract_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "".join(page.extract_text() for page in reader.pages)

def compare_text(pdf1, pdf2):
    text1, text2 = extract_text(pdf1), extract_text(pdf2)
    diff = difflib.unified_diff(
        text1.splitlines(),
        text2.splitlines(),
        fromfile="before.pdf",
        tofile="after.pdf",
    )
    return list(diff)
    

def main():
    if len(sys.argv) != 3:
        print("Usage: python app.py <file1.pdf> <file2.pdf>")
        print(f"Available files: pdf1.pdf, pdf2.pdf")
        sys.exit(1)
    
    file1, file2 = sys.argv[1], sys.argv[2]
    
    try:
        with open(file1, "rb") as f1, open(file2, "rb") as f2:
            pdf1_bytes = f1.read()
            pdf2_bytes = f2.read()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("Converting PDFs to images...")
    try:
        doc1 = pymupdf.open(stream=pdf1_bytes, filetype="pdf")
        doc2 = pymupdf.open(stream=pdf2_bytes, filetype="pdf")
        images1 = [page.get_pixmap(dpi=150).pil_image() for page in doc1]
        images2 = [page.get_pixmap(dpi=150).pil_image() for page in doc2]
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        sys.exit(1)

    max_pages = max(len(images1), len(images2))
    print(f"PDF 1 pages: {len(images1)}, PDF 2 pages: {len(images2)}")

    image_diffs_found = 0
    for i in range(max_pages):
        img1 = images1[i] if i < len(images1) else None
        img2 = images2[i] if i < len(images2) else None
        
        if img1 is None or img2 is None:
            print(f"Page {i+1}: page count mismatch")
            continue
            
        if img1.size != img2.size:
            print(f"Page {i+1}: size mismatch {img1.size} vs {img2.size}")
            continue

        annotated = compare_images(img1, img2)
        if annotated is not None:
            image_diffs_found += 1
            out_path = f"diff_page_{i+1}.png"
            annotated.save(out_path)
            print(f"Page {i+1}: differences found -> {out_path}")

    if image_diffs_found == 0:
        print("No visual differences found between pages.")

    print("\n--- Text diff ---")
    differences = compare_text(pdf1_bytes, pdf2_bytes)
    if differences:
        for line in differences:
            print(line)
    else:
        print("No text differences found.")

if __name__ == "__main__":
    main()