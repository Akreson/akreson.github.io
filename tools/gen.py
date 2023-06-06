import os
import sys
import datetime
import math

# this script was made to serve my needs, parser for front matter isn't bullet proof
# so it can not work for you style of front matter

PAGES_PER_PAGE = 10
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
POST_PATH = os.path.abspath(SCRIPT_PATH+"/../_posts")
CATEG_PATH = os.path.abspath(SCRIPT_PATH+"/../_categs_clet")
TAG_PATH = os.path.abspath(SCRIPT_PATH+"/../_tags_clet")
PAGES_PATH = os.path.abspath(SCRIPT_PATH+"/../_pages_clet")

class TokenType:
    UNKNOWN = 0
    END_OF_STREAM = 1
    OPEN_PAREN = 2
    CLOSE_PAREN = 3
    COLON = 4
    SEMICOLON = 5
    ASTERISK = 6
    OPEN_BRACKET = 7
    CLOSE_BRACKET = 8
    OPEN_BRACE = 9
    CLOSE_BRACE = 10
    COMA = 11
    SIMPLE_STR = 12
    FIELD_PARAM = 13
    COMMENT = 14
    DASH = 15

ONE_CHAR_TOKEN = {
    ord('\0'): TokenType.END_OF_STREAM,
    ord('('): TokenType.OPEN_PAREN,
    ord(')'): TokenType.CLOSE_PAREN,
    ord(':'): TokenType.COLON,
    ord(';'): TokenType.SEMICOLON,
    ord('*'): TokenType.ASTERISK,
    ord('['): TokenType.OPEN_BRACKET,
    ord(']'): TokenType.CLOSE_BRACKET,
    ord('{'): TokenType.OPEN_BRACE,
    ord('}'): TokenType.CLOSE_BRACE,
    ord(','): TokenType.COMA,
    ord('#'): TokenType.COMMENT,
    ord('-'): TokenType.DASH
}

END_OF_LINE = {
    ord('\n'):0,
    ord('\r'):0
}

WHITE_SPACE = {
    ord(' '): 0,
    ord('\t'):0,
    ord('\v'):0,
    ord('\f'):0
}

def panic(msg):
    print(msg)
    sys.exit(-1)

class Field:
    TAG = "tag"
    TAG_ARR = "tags"
    CATEG = "category"
    CATEG_ARR = "categories"
    DATE = "date"
    PIN = "pin"
    LANG_UNIQ = "languniq"
    MATH = "math"

class Token:
    def __init__(self):
        self.type = TokenType.UNKNOWN
        self.str = None

class ParseRange:
    def __init__(self, start, end):
        self.start = start
        self.at = start
        self.end = end
    
    def finish(self):
        result = False
        if self.at >= self.end:
            result = True
        return result

    def print(self):
        print("start {0} at {1} end {2}".format(self.start, self.at, self.end))

class DatePram():
    def __init__(self):
        self.year = 0
        self.month = 0
        self.day = 0
        self.hour = 0
        self.min = 0
        self.sec = 0
        self.zone = 0

    def print(self):
        print("year ", self.year)
        print("month ", self.month)
        print("day ", self.day)
        print("hour ", self.hour)
        print("min ", self.min)
        print("sec ", self.sec)
        print("zone ", self.zone)

class PostsData:
    def __init__(self):
        self.agg_tags = dict()
        self.agg_categ = dict()
        self.posts = dict()
    
    def agg_post(self, name, post_data, path):
        if name in self.posts:
            panic("duplicate post {0} in {1}".format(name, path))
        
        if Field.TAG in post_data and Field.TAG_ARR in post_data:
            panic("tag and tags specified in {0}/{1}".format(path, name))
        elif Field.TAG_ARR in post_data:
            for tag in post_data[Field.TAG_ARR]:
                self.agg_tags[tag] = 0
        elif Field.TAG in post_data:
            post_data[Field.TAG_ARR] = [post_data[Field.TAG][0]]
            self.agg_tags[post_data[Field.TAG_ARR][0]] = 0
            del post_data[Field.TAG]
        else:
            panic("no tags specified in {0}/{1}".format(path, name))

        if Field.CATEG in post_data and Field.CATEG_ARR in post_data:
            panic("category and categories specified in {0}/{1}".format(path, name))
        elif Field.CATEG_ARR in post_data:
            for tag in post_data[Field.CATEG_ARR]:
                self.agg_categ[tag] = 0
        elif Field.CATEG in post_data:
            post_data[Field.CATEG_ARR] = [post_data[Field.CATEG][0]]
            self.agg_categ[post_data[Field.CATEG_ARR][0]] = 0
            del post_data[Field.CATEG]
        else:
            panic("no categories specified in {0}/{1}".format(path, name))

        if Field.DATE not in post_data:
            panic("no data specified in {0}/{1}".format(path, name))

        self.posts[name] = post_data

def print_substr_from_byte(data, start, end):
    arr = data[start:end]
    print(arr.decode('utf-8'))

def get_name_field(data, parse_range, err_path):
    skip_space(data, parse_range)

    eol_index = get_eol_index(data, parse_range)
    itr = eol_index

    temp_result = None
    if data[parse_range.at] == ord('"'):
        while data[itr] != ord('"') and itr != parse_range.at:
            itr -= 1

        if (itr - parse_range.at) < 2:
            print_substr_from_byte(data, parse_range.at, eol_index)
            panic("Invalid single param val in {0}".format(err_path))

        parse_range.at += 1
        sub_itr = parse_range.at
        while sub_itr != itr:
            if data[sub_itr] == ord('"'):
                print_substr_from_byte(data, parse_range.at, eol_index)
                panic("Invalid single param val in {0}".format(err_path))
            sub_itr += 1
        temp_result = data[parse_range.at:itr]
    elif is_alpha(data[parse_range.at]):
        itr = skip_space_back_itr(itr, data)
        temp_result = data[parse_range.at:(itr+1)]
    else:
        print_substr_from_byte(data, parse_range.at, eol_index)
        panic("Invalid single param val in {0}".format(err_path))
    
    result = []
    result.append(temp_result.decode("utf-8"))
    parse_range.at = eol_index
    return result

def get_list_name_field(data, parse_range, err_path):
    skip_space(data, parse_range)

    eol_index = get_eol_index(data, parse_range)
    itr = eol_index

    result_params = []
    if data[parse_range.at] == ord('['):
        while data[itr] != ord(']') and itr != parse_range.at:
            itr -= 1
        
        if (data[parse_range.at + 1] == ord('"') and (itr - parse_range.at) < 4) or (itr - parse_range.at) < 2:
            print_substr_from_byte(data, parse_range.at, eol_index)
            panic("Invalid array param vals {0}".format(err_path))

        sub_itr = parse_range.at

        comma_index_arr = []
        while sub_itr != itr:
            if data[sub_itr] == ord(','):
                comma_index_arr.append(sub_itr)
            sub_itr += 1
        
        comma_index_arr.append(itr)

        prev_index = parse_range.at
        for end_val_index in comma_index_arr:
            end_index = end_val_index
            parse_range.at = prev_index + 1
            skip_space(data, parse_range)

            if data[parse_range.at] == ord('"'):
                sub_itr = end_index
                while data[sub_itr] != ord('"') and sub_itr != parse_range.at:
                    sub_itr -= 1
                if (parse_range.at - sub_itr) < 2:
                    print_substr_from_byte(data, parse_range.at, eol_index)
                    panic("Invalid array param vals {0}".format(err_path))
                end_index = sub_itr
                parse_range.at += 1

            end_index = skip_space_back_itr(end_index, data)

            temp_result = data[parse_range.at:end_index]
            result_params.append(temp_result)

            prev_index = end_val_index
    else:
        end_index = skip_space_back_itr(eol_index, data)

        last_start = parse_range.at
        while parse_range.at <= end_index:
            if data[parse_range.at] == ord(' ') or parse_range.at == end_index:
                temp_result = data[last_start:parse_range.at]
                result_params.append(temp_result)
                last_start = parse_range.at + 1
            parse_range.at += 1


    result_params = [item.decode("utf-8") for item in result_params]
    parse_range.at = eol_index
    return result_params

# was lazy set correct error log because nobody except me will use it anyway
def get_data_str(data, parse_range, err_path):
    eol_index = get_eol_index(data, parse_range)
    end_index = skip_space_back_itr(eol_index, data)
    skip_space(data, parse_range)

    date_str = data[parse_range.at:end_index]
    date_str = date_str.decode("utf-8")
    date_arr = date_str.split(' ')

    date_param = DatePram()

    if len(date_arr[0]) != 10:
        panic("{0}: date part of _date_ field is invalid".format(err_path))

    if len(date_arr[1]) != 8:
        panic("{0}: time part of _date_ field is invalid".format(err_path))
    
    if len(date_arr[2]) != 5:
        panic("{0}: timezone part of _date_ field is invalid".format(err_path))

    date_part = date_arr[0].split('-')
    time_part = date_arr[1].split(':')

    if len(date_part) != 3 or len(date_part[0]) != 4 or len(date_part[1]) != 2 or len(date_part[2]) != 2:
        panic("{0}: date part of _date_ field is invalid".format(err_path))
    if (not date_part[0].isnumeric()) or (not date_part[1].isnumeric()) or (not date_part[2].isnumeric()):
        panic("{0}: date part of _date_ field contain non numeric char".format(err_path))

    if len(time_part) != 3 or len(time_part[0]) != 2 or len(time_part[1]) != 2 or len(time_part[2]) != 2:
        panic("{0}: time part of _date_ field is invalid".format(err_path))
    if (not time_part[0].isnumeric()) or (not time_part[1].isnumeric()) or (not time_part[2].isnumeric()):
        panic("{0}: time part of _date_ field contain non numeric char".format(err_path))
    
    if (not date_arr[2][1:3].isnumeric()) and ((date_arr[2][0] != '-') or (date_arr[2][0] != '+')):
        panic("{0}: timezone part of _date_ field is invalid".format(err_path))
    
    date_param.zone = int(date_arr[2][1:3])
    if date_param.zone > 24:
        panic("{0}: timezone part of _date_ out of range".format(err_path))

    if date_arr[2][0] == '-':
        date_param.zone *= -1
    
    date_param.year = int(date_part[0])
    date_param.month = int(date_part[1])
    date_param.day = int(date_part[2])
    date_param.hour = int(time_part[0])
    date_param.min = int(time_part[1])
    date_param.sec = int(time_part[2])

    # bare check
    if date_param.year > 9999 or date_param.month > 12 or date_param.day > 31:
        panic("{0}: date part of _date_ out of range".format(err_path))
    
    if date_param.hour > 23 or date_param.min > 59 or date_param.sec > 59:
        panic("{0}: date part of _date_ out of range".format(err_path))

    parse_range.at = eol_index
    result_date = datetime.datetime(date_param.year, date_param.month, date_param.day,
        date_param.hour, date_param.min, date_param.sec,
        tzinfo=datetime.timezone(datetime.timedelta(hours=date_param.zone)))   
    return result_date


def get_bool_status(data, parse_range, err_path):
    eol_index = get_eol_index(data, parse_range)
    end_index = skip_space_back_itr(eol_index, data)
    skip_space(data, parse_range)

    temp_result = data[parse_range.at:end_index]
    temp_result = temp_result.decode("utf-8")

    result = None
    parse_range.at = eol_index
    if temp_result == "true":
        result = True
    elif temp_result == "false":
        result = False
    else:
        print_substr_from_byte(data, parse_range.at, eol_index)
        panic("Invalid bool param val {0}".format(err_path))

    parse_range.at = eol_index
    return result

def is_whitespace(byte):
    result = False
    if byte in WHITE_SPACE:
        result = True
    return result

def is_endofline(byte):
    result = False
    if byte in END_OF_LINE:
        result = True
    return result

def is_alpha(byte):
    result = False
    if byte >= ord('a') and byte <= ord('z') or byte >= ord('A') and byte <= ord('Z'):
        result = True
    return result

def get_eol_index(data, parse_range):
    result_index = parse_range.at
    while parse_range.at < parse_range.end:
        if is_endofline(data[result_index]):
            break
        result_index += 1
    return result_index

def skip_whitespace(data, parse_range):
    while parse_range.at < parse_range.end:
        byte = data[parse_range.at]
        if is_endofline(byte) or is_whitespace(byte):
            parse_range.at += 1
        else:
            break

def skip_space(data, parse_range):
    while data[parse_range.at] == ord(' '):
        parse_range.at += 1

def skip_space_back_itr(itr, data):
    while itr >=0 and data[itr] == ord(' '):
        itr -= 1
    return itr

def skip_to_next_line_itr(itr, data, size):
    while itr < size:
        if data[itr] == ord("\n"):
            itr += 1
            break;    
        itr += 1

    return itr

def skip_to_next_line(data, parse_range):
    parse_range.at = skip_to_next_line_itr(parse_range.at, data, parse_range.end)

def find_parse_range(data, size):
    result = [0, 0]
    fill_index = 0

    itr = 0
    last_index = size - 1

    while itr < last_index or fill_index < 2:
        to_end = last_index - itr
        if data[itr] == ord('-') and to_end >= 2:
            if data[itr + 1] == ord('-') and data[itr + 2] == ord('-'):
                if fill_index == 0:
                    itr = skip_to_next_line_itr(itr, data, size)
                    result[0] = itr
                else:
                    result[1] = itr - 1
                    break
                fill_index += 1
        itr += 1
    
    return ParseRange(result[0], result[1])

def get_token(data, parse_range):
    result_token = Token()
    if data[parse_range.at] in ONE_CHAR_TOKEN:
        result_token.type = ONE_CHAR_TOKEN[data[parse_range.at]]
        parse_range.at += 1
    else:
        result_token.type = TokenType.SIMPLE_STR
        skip_whitespace(data, parse_range)

        start = parse_range.at
        while is_alpha(data[parse_range.at]) or (data[parse_range.at] == ord('_')):
            parse_range.at += 1
        end = parse_range.at
        
        temp_arr = data[start:end]
        result_token.str = temp_arr.decode('utf-8')

    return result_token

PARSE_FIELD_LIST = {
    Field.TAG : get_name_field,
    Field.TAG_ARR : get_list_name_field,
    Field.CATEG : get_name_field,
    Field.CATEG_ARR : get_list_name_field,
    Field.DATE : get_data_str,
    Field.PIN : get_bool_status,
    Field.LANG_UNIQ : get_bool_status,
    Field.MATH : get_bool_status
}

def parse_post_params(data, size, err_path):
    result_post_params = dict()
    parse_range = find_parse_range(data, size)

    if parse_range.start != 0 and parse_range.end != 0:
        parsing = True

        while parsing and parse_range.finish() == False:
            skip_whitespace(data, parse_range)
            token = get_token(data, parse_range)

            if token.type == TokenType.SIMPLE_STR:
                skip_space(data, parse_range)
                next_token = get_token(data, parse_range)
                if next_token.type == TokenType.COLON:
                    if token.str in PARSE_FIELD_LIST:
                        parse_field_func = PARSE_FIELD_LIST[token.str]
                        field_val_arr = parse_field_func(data, parse_range, err_path)
                        result_post_params[token.str] = field_val_arr
                    else:
                        skip_to_next_line(data, parse_range)
                else:
                    panic("{0}: unexpected token after \"{1}\" in the front matter. Please change the front matter or modify parse script".format(err_path, token.str))
            elif token.type == TokenType.COMMENT or token.type == TokenType.DASH:
                skip_to_next_line(data, parse_range)
            elif token.type == TokenType.END_OF_STREAM:
                parsing = False
            else:
                parsing = False

    return result_post_params


def collect_lang_folder_data(folder_scan_item):
    lang_dir = os.scandir(folder_scan_item.path)
    posts_data = PostsData()
    
    for item in lang_dir:
        if item.is_file():
            if item.name in posts_data.posts:
                panic("Error: duplicate file {0} in {1}".format(item.name, folder_scan_item.path))
            else:
                file_stat = item.stat()
                
                read_size = 1024
                if file_stat.st_size < read_size:
                    read_size = file_stat.st_size
                
                try:
                    file_handle = open(item.path, "rb")
                except OSError as e:
                    panic(str(e))

                data = file_handle.read(read_size)
                post_params = parse_post_params(data, read_size, item.path)
                posts_data.agg_post(item.name, post_params, folder_scan_item.path)
                file_handle.close()
        else:
            panic("Error: {0} is not a file".format(item.path))

    lang_dir.close()
    return posts_data


def collect_posts_info(posts_folders):
    post_dir = os.scandir(POST_PATH)

    for item in post_dir:
        if item.is_dir():
            if item.name in posts_folders:
                panic("Error: folder \"{0}\" already exist".format(item.name))
            else:
                posts_data = collect_lang_folder_data(item)
                posts_folders[item.name] = posts_data
        
        if item.is_file():
            panic("Error: out of scope file {0}".format(item.path))
    
    post_dir.close()

def check_posts_filed(folder0, folder0_data, folder1, folder1_data, post_name, field, err_list):
    if len(folder0_data[field]) == len(folder1_data[field]):
        set0 = set(folder0_data[field])
        set1 = set(folder1_data[field])
        diff = set0.difference(set1)
        if len(diff) > 0:
            err_msg = "post {0} in _{1}_ and _{2}_ have different list of {3}".format(post_name, folder0, folder1, field)
            err_list.append(err_msg)
    else:
        err_msg = "post {0} in _{1}_ and _{2}_ have different amount of {3}".format(post_name, folder0, folder1, field)
        err_list.append(err_msg)

def check_posts_lang_copy(posts_folders, err_list):
    folders_name = posts_folders.keys()
    key_dict = dict()

    for name in folders_name:
        key_dict[name] = dict()
        for post_name in posts_folders[name].posts:
            key_dict[name][post_name] = 0
    
    for name in folders_name:
        itr_folders = [val for val in folders_name if val != name]

        lang_posts = key_dict[name]
        for post_name in lang_posts:
            post_lang_data = posts_folders[name].posts[post_name]
            is_lang_uniq = False

            if Field.LANG_UNIQ in post_lang_data:
                is_lang_uniq = post_lang_data[Field.LANG_UNIQ]

            for itr_name in itr_folders:
                itr_dict = key_dict[itr_name]

                if is_lang_uniq:
                    if post_name in itr_dict:
                        err_msg = "post {0}/{1} is lang_uniq, copy of it should not exist in _{2}_".format(name, post_name, itr_name)
                        err_list.append(err_msg)
                        del itr_dict[post_name]
                else:
                    if post_name in itr_dict:
                        itr_post_data = posts_folders[itr_name].posts[post_name]

                        if Field.LANG_UNIQ in itr_post_data:
                            if itr_post_data[Field.LANG_UNIQ] == True:
                                err_msg = "post {0}/{1} is lang_uniq, copy of it should not exist in _{2}_".format(itr_name, post_name, name)
                                err_list.append(err_msg)

                        if post_lang_data[Field.DATE] != itr_post_data[Field.DATE]:
                            err_msg = "post {0} in _{1}_ and _{2}_ should have same date {3} - {4}".format(post_name, name, itr_name, str(post_lang_data[Field.DATE]), str(itr_post_data[Field.DATE]))
                            err_list.append(err_msg)
                        
                        err_msg = "post {0} in _{1}_ and _{2}_ should be pinned".format(post_name, name, itr_name)
                        post_has_pin = Field.PIN in post_lang_data
                        itr_has_pin = Field.PIN in itr_post_data
                        if post_has_pin and itr_has_pin:
                            if post_lang_data[Field.PIN] != itr_post_data[Field.PIN]:
                                err_list.append(err_msg)
                        elif post_has_pin or itr_has_pin:
                            err_list.append(err_msg)
                        
                        err_msg = "post {0} in _{1}_ and _{2}_ should have same \"math\" value".format(post_name, name, itr_name)
                        post_has_math = Field.MATH in post_lang_data
                        itr_has_math = Field.MATH in itr_post_data
                        if post_has_math and itr_has_math:
                            if post_lang_data[Field.MATH] != itr_post_data[Field.MATH]:
                                err_list.append(err_msg)
                        elif post_has_math or itr_has_math:
                            err_list.append(err_msg)

                        check_posts_filed(name, post_lang_data, itr_name, itr_post_data, post_name, Field.CATEG_ARR, err_list)
                        check_posts_filed(name, post_lang_data, itr_name, itr_post_data, post_name, Field.TAG_ARR, err_list)
                        
                        del itr_dict[post_name]
                    else:
                        err_msg = "post {0}/{1} should exist in _{2}_".format(name, post_name, itr_name)
                        err_list.append(err_msg)
        lang_posts.clear()

def check_start_up_paths():
    try:
        if not os.path.exists(POST_PATH):
            panic("_posts folder does not exist")

        if not os.path.exists(TAG_PATH):
            os.makedirs(TAG_PATH)
        if not os.path.exists(CATEG_PATH):
            os.makedirs(CATEG_PATH)
        if not os.path.exists(PAGES_PATH):
            os.makedirs(PAGES_PATH)
    except OSError as e:
        panic(e)

def create_collects_path(tag_path, categ_path, pages_path):
    try:
        if not os.path.exists(tag_path):
            os.makedirs(tag_path)
        if not os.path.exists(categ_path):
            os.makedirs(categ_path)
        if not os.path.exists(pages_path):
            os.makedirs(pages_path)
    except OSError as e:
        panic(e)

def open_file_write(folder_path, filename):
    path = os.path.join(folder_path, filename)
    try:
        file_handle = open(path, "w")
    except OSError as e:
        panic(str(e))
    return file_handle

def create_collect(name_dict, path, header_template):
    collect_dir = os.scandir(path)
    for item in collect_dir:
        if item.is_file():
            item_check_name = item.name.split(".")[0]
            if item_check_name not in name_dict:
                os.remove(os.path.join(path, item.name))
    collect_dir.close()

    for name in name_dict:
        file_handle = open_file_write(path, name+'.md')
        file_handle.write(header_template.format(name))
        file_handle.close()

def create_pages(posts_dict, pages_path, lang):
    pages_count = math.ceil(len(posts_dict)/PAGES_PER_PAGE);
    for i in range(2, pages_count+1):
        curr_page = 'page{0}.md'.format(i)

        prev_path = ''
        if (i-1) == 1:
            prev_path = '/{0}/'.format(lang)
        else:
            prev_path = '/{0}/{1}'.format(lang, 'page{0}'.format(i-1))

        has_next = 'true'
        next_path = ''
        if i != pages_count:
            next_path = '/{0}/{1}'.format(lang, 'page{0}'.format(i+1))
        else:
            has_next = 'false'
            next_path = '/'
  
        page_str = PAGE_HEADER_TEMPLATE.format(i, 'true', prev_path, has_next, next_path)
        #print(pages_path, curr_file_path)
        page_file = open_file_write(pages_path, curr_page)
        page_file.write(page_str)
        page_file.close()

TAG_HEADER_TEMPLATE = "---\ntitle: {0}\ntag: {0}\n---\n"
CATEG_HEADER_TEMPLATE = "---\ntitle: {0}\ncategory: {0}\n---\n"
PAGE_HEADER_TEMPLATE = "---\npagenum: {0}\nprevious_page: {1}\nprevious_page_path: {2}\nnext_page: {3}\nnext_page_path: {4}\n---\n"

def gen_collect(posts_folders):
    for lang_name in posts_folders:
        lang_posts = posts_folders[lang_name]

        tag_path = os.path.join(TAG_PATH, lang_name)
        categ_path = os.path.join(CATEG_PATH, lang_name)
        pages_path = os.path.join(PAGES_PATH, lang_name)

        create_collects_path(tag_path, categ_path, pages_path)
        create_collect(lang_posts.agg_tags, tag_path, TAG_HEADER_TEMPLATE)
        create_collect(lang_posts.agg_categ, categ_path, CATEG_HEADER_TEMPLATE)
        create_pages(lang_posts.posts, pages_path, lang_name)

def main():
    check_start_up_paths()

    posts_folders = dict()
    collect_posts_info(posts_folders)

    err_list = []
    check_posts_lang_copy(posts_folders, err_list)

    if len(err_list) == 0:
        gen_collect(posts_folders)
    else:
        for err in err_list:
            print(err)

if __name__ == "__main__":
    main()