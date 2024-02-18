import zipfile
from io import BytesIO
import random
from statistics import mode
import time
import csv

import requests
from bs4 import BeautifulSoup

from pysubs2 import SSAFile
from googletrans import Translator

def filter_info(element):
    url = "https://www.opensubtitles.org" + element.find("a", class_="bnone")["href"]
    resp_down_page = requests.get(url)
    down_page_soup = BeautifulSoup(resp_down_page.text, "html.parser")
    down_btn = down_page_soup.find(id="bt-dwl-bt")
    content = requests.get("https://www.opensubtitles.org" + down_btn["href"]).content
    filedowned = BytesIO(content)
    if not zipfile.is_zipfile(filedowned):
        print(down_btn["href"])
        raise Exception("File is not supported")

    with zipfile.ZipFile(filedowned, mode="r") as zipf:
        for ff in zipf.infolist():
            if ff.filename.endswith(".srt"):
                return zipf.read(ff.filename)

def get_best_sub(
        best_lang="zht",
        movie_name=None,
        season=None,
        episode=None,
        imdb_id=None
        ):
    # TODO: make this cleaner, add language output
    search_url = 'https://www.opensubtitles.org/en/search2'
    best_lang = best_lang.lower()
    lang_code = LanguageCode()
    best_lang_osub = lang_code.get_opensub(best_lang)
    best_lang_gtrans = lang_code.get_gtrans(best_lang)
    if best_lang_osub is None:
        raise ValueError(f"Language not supported, see the language_codes.csv for supported languages.")

    def get_sub(lang, check_lang=True):
        params = {
            "MovieName": (movie_name if not imdb_id else "") or "",
            "id": 81,  # I think this is random number
            "action": "search",
            "SubLanguageID": lang,
            "Season": season or "",
            "Episode": episode or "",
            "SubSumCD": "",
            "Genre": "",
            "MovieByteSize": "",
            "MovieLanguage": "",
            "MovieImdbRatingSign": 1,
            "MovieImdbRating": "",
            "MovieCountry": "",
            "MovieYearSign": 1,
            "MovieYear": "",
            "MovieFPS": "",
            "SubFormat": "",
            "SubAddDate": "",
            "Uploader": "",
            "IDUser": "",
            "Translator": "",
            "IMDBID": imdb_id or "",
            "MovieHash": "",
            "IDMovie": ""
        }
        params["SubLanguageID"] = lang
        resp = requests.get(search_url, params=params)
        soup = BeautifulSoup(resp.text, "html.parser")

        if check_lang:
            if lang_code.get_opensub(lang) is None:
                raise ValueError(f"Language not supported, see the language_codes.csv for supported languages.")
        
        tables = soup.find(id="search_results")
        if tables is not None:
            best_one = tables.find(class_=["change", "expandable"])
            if best_one is not None:
                return filter_info(best_one).decode()
        return None

    sub = get_sub(best_lang_osub, check_lang=False)
    if sub is not None:
        return SSAFile.from_string(sub)
    
    # best one not found, finding english
    sub = get_sub("eng", check_lang=False)
    if sub is not None:
        # translate to best_lang
        return translate_sub(sub, best_lang_gtrans, "en")
    
    # english not found, get anything
    sub = get_sub("all", check_lang=False)
    if sub is not None:
        return translate_sub(sub, best_lang_gtrans, "auto")
    
    # found nothing
    raise ValueError("This movie cannot be not found.")

def clean_text(text):
    out_text = text
    if "\\N" in text:
        if text.strip().startswith("-"):
            out_text = out_text.replace("\\N\r", "\n").replace("\r\\N", "\n").replace("\\N", "\n")
        else:
            # the \n is because the line is too long
            out_text = out_text.replace("\\N\r", " ").replace("\r\\N", " ").replace("\\N", " ")
    return out_text

# Define function to translate subtitle text
def batch_translate_text(text_lines, translator, targ, src=None, max_characters=10000, delay=0.3):
    MAX_RETRY = 10
    if not text_lines:
        return text_lines
    out_translations = []

    # batch the most lines possible
    i = 1
    char_count = len(text_lines[0])
    this_batch = [text_lines[0]]
    while i < len(text_lines):
        print(f"{i}/{len(text_lines)}", end="\r")
        if char_count + len(text_lines[i]) < max_characters:
            this_batch.append(text_lines[i])
            char_count += len(text_lines[i])
            i += 1
        else:
            # translate this batch
            j = 0
            while True:
                try:
                    translations = translator.translate(this_batch, src=(src or "auto"), dest=targ)
                    break
                except Exception as e:
                    if j < MAX_RETRY:
                        j += 1
                        time.sleep(delay * 2 ** j)
                        continue
                    else:
                        raise Exception("Failed to translate")
            out_translations.extend(translations)
            this_batch = []
            char_count = 0
            time.sleep(delay)
        
    if this_batch:
        translations = translator.translate(this_batch, src=(src or "auto"), dest=targ)
        out_translations.extend(translations)

    return out_translations
    # translation = translator.translate(clean_text(text), src=(src or "auto"), dest=targ)
    # return translation.text

def determine_lang_sub(sub, translator):
    sampled_langs = []
    for ind in random.sample(range(len(sub)), min(len(sub), 20)):
        sampled_langs.append(translator.detect(sub[ind].text).lang)
    return mode(sampled_langs)

def translate_sub(sub_str, target_lang, source_lang=None):
    # TODO: use some bulk features

    translator = Translator()
    subs = SSAFile.from_string(sub_str)
    srclang = determine_lang_sub(subs, translator)
    subs_texts = [clean_text(line.text) for line in subs]

    # translations = translator.translate([t for t in subs_texts if t], src=srclang, dest=target_lang)[::-1]
    translations = batch_translate_text(subs_texts, translator, target_lang, src=srclang)[::-1]

    for i, line in enumerate(subs):
        if not line.text:
            continue
        try:
            line.text = translations.pop().text.replace("\n", "\\N")
        except IndexError:
            print("Error at", i)
            break
        
    print("\nTranslating done.")
    return subs


class LanguageCode:
    def __init__(self, lang_code_csv='language_codes.csv') -> None:
        with open(lang_code_csv, newline='') as f:
            reader = csv.reader(f)
            self.data = list(reader)  # [(Language, gtrans, opensub)]
    
    def get_gtrans(self, lang):
        for row in self.data:
            if lang.lower() in row:
                print(row)
                return row[1]
        return None
    
    def get_opensub(self, lang):
        for row in self.data:
            if lang.lower() in row:
                return row[2]
        return None



def main():
    out = get_best_sub(best_lang="zh-TW", imdb_id="tt15314262")
    # translated = translate_sub(sub_str, target_lang)

    out.save("translated.srt")


if __name__ == "__main__":
    main()
