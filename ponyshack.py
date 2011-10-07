#!/usr/bin/python2

import web
import re
import os
import subprocess
import logging
import hashlib
import psycopg2
import random
import urllib
import crypt


dbengine=psycopg2
dbparam="dbname=ponyshack user=codl"

domain="http://ponyshack.aquageek.net"

picsdir = "/srv/ponyshack/ps"
thumbsdir = "/srv/ponyshack/pst"
if not os.path.exists(picsdir):
    os.makedirs(picsdir)
if not os.path.exists(thumbsdir):
    os.makedirs(thumbsdir)

def dbconnect_gen(func):
    def newfunc(*args, **kwargs):
        conn = dbengine.connect(dbparam)
        cursor = conn.cursor()
        for data in func(*args, cursor=cursor, **kwargs):
            yield data
        conn.commit()
        conn.close()
    return newfunc

def dbconnect(func):
    def newfunc(*args, **kwargs):
        conn = dbengine.connect(dbparam)
        cursor = conn.cursor()
        returnvalue = func(*args, cursor=cursor, **kwargs)
        conn.commit()
        conn.close()
        return returnvalue
    return newfunc

def escape(s, nbsp=False):
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    if nbsp:
        s = s.replace(" ", "&nbsp;")
    return s

def sanitize_url(url):
    url = url.strip()
    if url.find(".") == -1:
        return ""
    elif url.find("http://") != 0 and url.find("https://") != 0:
        return urllib.quote("http://"+url, "/:#?&=")
    else:
        return urllib.quote(url, "/:#?&=")

def make_thumb(source, fileformat, dest):
    if fileformat == "GIF":
        args = "gifsicle --batch -O2 %s"%(source,)
        subprocess.call(args.split())
        args = "gifsicle -o %s --resize _x100 -O2 %s"%(dest, source)
        subprocess.call(args.split())
    elif fileformat == "JPEG":
        args = "convert %s -quality 85 -resize x100 %s"%(source, dest)
        subprocess.call(args.split())
    elif fileformat == "PNG":
        args = "convert %s -resize x100 %s"%(source, dest)
        subprocess.call(args.split())
        args = "optipng -o4 %s %s"%(source,dest) ### to be tried out,
        subprocess.call(args.split())              # might be too slow

@dbconnect
def get_powers(cursor):
    cookies = web.cookies(user_id=0, auth=0)
    user_id = int(cookies["user_id"])
    user_auth = int(cookies["auth"])
    cursor.execute("""
        SELECT user_type FROM public.user
        WHERE user_id = %s AND user_auth = %s
        ;""", (user_id, user_auth)) # "user" seems to be reserved
    user = cursor.fetchone()
    if user:
        # refresh cookies
        web.setcookie("user_id", str(user_id), 3600*24*365)
        web.setcookie("auth", str(user_auth), 3600*24*365)
        return user[0]
    else:
        return -1

def is_logged_in():
    return get_powers() >= 0

def has_submit_powers():
    #return get_powers() >= 1
    return True # LOL EVERYONE SUBMITS

def has_alicorn_powers():
    return get_powers() == 4

@dbconnect
def get_tag_id(tag, flatten = True, create = True, cursor = None):
    tag = tag.lower().strip().replace('+', " ").replace('"', ' ')
    # escaping " upstream because it's a pain to escape and unescape everywhere
    cursor.execute("SELECT synonym,tag_id FROM tag WHERE tag_name = %s", (tag,))
    result = cursor.fetchone()
    if result and flatten and result[0]: return result[0]
    elif result: return result[1]
    elif create:
        cursor.execute("""INSERT INTO tag (tag_name) VALUES (%s);
                SELECT tag_id FROM tag WHERE tag_name = %s;
                """, (tag, tag))
        return cursor.fetchone()[0]
    else:
        logging.info("Nonexistant tag %s"%tag)
        return None

@dbconnect
def get_tag_name(tag_id=None, tag_id_36=None, flatten=True, cursor = None):
    if tag_id_36:
        tag_id=int(tag_id_36, 36)

    cursor.execute("SELECT tag_name, synonym FROM tag WHERE tag_id = %s", (tag_id,))
    tag = cursor.fetchone()
    if flatten and tag[1]:
        cursor.execute("SELECT tag_name FROM tag WHERE tag_id = %s", (tag[1],))
        tag = cursor.fetchone()
    return tag[0]


@dbconnect
def add_tag(tag_id, image_id, cursor=None):
    cursor.execute("""
        SELECT tag_id FROM tag_mapping
        WHERE tag_id = %s AND image_id = %s
        ;""", (tag_id, image_id))
    if cursor.fetchone():
        return False
    else:
        cursor.execute("""
            INSERT INTO tag_mapping (tag_id, image_id)
            VALUES (%s, %s);""", (tag_id, image_id))
        return True

@dbconnect
def rm_tag(tag_id, image_id, cursor=None):
    cursor.execute("""
        SELECT tag_id FROM tag_mapping
        WHERE tag_id = %s AND image_id = %s
        ;""", (tag_id, image_id))
    if cursor.fetchone():
        cursor.execute("""
            DELETE FROM tag_mapping
            WHERE tag_id = %s AND image_id = %s
            ;""", (tag_id, image_id))
        cursor.execute("""
            SELECT tag_id FROM tag_mapping
            WHERE tag_id = %s
            ;""", (tag_id,))
        if not cursor.fetchone():
            cursor.execute("""
                DELETE FROM tag
                WHERE tag_id = %s
                ;""", (tag_id,))
        return True
    else:
        return False

class all:
    @dbconnect
    def GET(self, cursor=None):
        cursor.execute("""
                SELECT image_id FROM image
                ORDER BY views DESC
                ;"""
                );
        images = cursor.fetchall()
        html = header(page_title = "all",
                search_box = "all",
                title = "Ponyshack : Viewing all")
        html += "<div class='imageriver'>"
        for image in images:
            html += image_link(image_id = image[0])
        html += "</div>"
        html += footer()
        return html

class search:
    @dbconnect
    def GET(self, search, cursor = None):
        search = search.replace("+", " ")
        taglist = search.split(",")
        temptaglist = []
        for tag in taglist:
            if tag.strip() != "":
                temptaglist.append(get_tag_id(tag.strip()))
        taglist = tuple(temptaglist)
        if taglist == ():
            raise web.seeother(domain+"/")
        cursor.execute("""
                WITH matching as (
                    SELECT image_id FROM tag_mapping
                    WHERE tag_id IN %s
                    GROUP BY image_id HAVING count(*) = %s
                )
                SELECT image_id FROM
                matching NATURAL INNER JOIN image
                ORDER BY views DESC
                ;""",
                (taglist, len(taglist)));
        images = cursor.fetchall()
        html = header(page_title = search, search_box = search)
        html += """<div class="imageriver">"""
        if len(images) == 0 :
            html += "Nothing to see here, sorry"
        else:
            for image in images:
                html += image_link(image_id = image[0])
        html += "</div>"
        return html + footer()

@dbconnect
def tag_link(tag_name = None, tag_id = None, cursor = None):
    if not tag_name and not tag_id: return None
    elif not tag_name:
        cursor.execute("""
            SELECT tag_name FROM tag WHERE tag_id = %s;
            """, (tag_id,))
        tag_name = cursor.fetchone()[0]
    html = "<a href='/%s' class='tag'>%s</a>"%(urllib.quote(tag_name), escape(tag_name, nbsp=True))
    return html

class index:
    @dbconnect
    def GET(self, cursor = None):
        html = header() + """
        <p class="tag_list">Most frequent tags : """
        cursor.execute("""
            WITH tag_ids as (
                SELECT tag_id, count(*) count FROM tag_mapping
                GROUP BY tag_id
                )
            SELECT tag_name FROM
            tag_ids NATURAL INNER JOIN tag
            WHERE count > 1
            ORDER BY count DESC LIMIT 40
            ;""")
        for tag in cursor:
            name = tag[0]
            html += tag_link(name) + " "
        html += "</p><h3>Most recent images</h3><div class='imageriver'>"
        cursor.execute("""
            select image_id FROM image
            ORDER BY time DESC LIMIT 20
            ;""")
        for image in cursor:
            html += image_link(image_id = image[0])
        html += """</div><p class="tag_list">Some random tags : """
        cursor.execute("""
            WITH tag_ids as (
                SELECT tag_id, count(*) count FROM tag_mapping
                GROUP BY tag_id
                )
            SELECT tag_name FROM
            tag NATURAL INNER JOIN tag_ids
            WHERE synonym ISNULL AND count > 0
            ORDER BY random() DESC LIMIT 50
            ;""")
        for tag in cursor:
            name = tag[0]
            html += tag_link(name) + " "
        html += "</p>"+footer()
        return html

class download:
    @dbconnect_gen
    def GET(self, imageid, cursor=None):
        imageid = int(imageid.split(".")[0], 36)
        cursor.execute("""
            UPDATE image SET views = views+1 WHERE image_id = %s;
            SELECT location, mimetype FROM image
            WHERE image_id = %s
            ;
            """, (imageid, imageid))
        image = cursor.fetchone()
        web.header("Content-Type", image[1])
        web.header("Transfer-Encoding", "chunked")
        web.header("Cache-Control", "public, max-age=31536000") # a year
        f = open(image[0], "rb")
        data = f.read(10000)
        while data:
            yield data
            data = f.read(10000)
class thumbnail:
    @dbconnect_gen
    def GET(self, imageid, cursor=None):
        imageid = int(imageid.split(".")[0], 36)
        cursor.execute("""
            SELECT thumb_location, mimetype FROM image
            WHERE image_id = %s
            ;
            """, (imageid,))
        image = cursor.fetchone()
        web.header("Content-Type", image[1])
        web.header("Transfer-Encoding", "chunked")
        web.header("Cache-Control", "public, max-age=31536000") # a year
        f = open(image[0], "rb")
        data = f.read(1000)
        while data:
            yield data
            data = f.read(1000)

class redirect:
    def GET(self):
        raise web.seeother(domain+"/")
class search_nojs:
    def GET(self):
        raise web.seeother(domain+"/"+web.input(q="").q)

class tags:
    @dbconnect
    def GET(self, cursor = None):
        if not has_alicorn_powers:
            raise web.seeother(domain+"/")
        html = header(page_title="Managing tags")
        webinput = web.input(tag_name=None, delete=None, new_name=None, synonym="THIS IS A DUMMY VALUE")
        if webinput.tag_name:
            if webinput.new_name:
                if get_tag_id(webinput.new_name, create=False):
                    html+="""A tag with that name already exists!"""
                    ### TODO actually overwrite the tag
                else:
                    cursor.execute("""
                        UPDATE tag SET tag_name = %s WHERE tag_name = %s;
                    """, (webinput.new_name, webinput.tag_name))
                    html+="""Renamed!"""
            if webinput.synonym != "THIS IS A DUMMY VALUE":
                tag_id = get_tag_id(webinput.tag_name.strip(" ,"), flatten=False)
                if webinput.synonym == '':
                    cursor.execute("""
                        UPDATE tag SET synonym = NULL WHERE tag_id = %s;
                        """, (tag_id,))
                    html+="Unsynonym'd!"
                else:
                    synonym_id = get_tag_id(webinput.synonym.strip(" ,"))
                    if tag_id == synonym_id:
                        html+="What were you thinking?"
                    else:
                        cursor.execute("""
                            UPDATE tag_mapping SET tag_id = %s WHERE tag_id = %s;
                            UPDATE tag SET synonym = %s WHERE synonym = %s;
                            UPDATE tag SET synonym = %s WHERE tag_id = %s;
                            """, (synonym_id, tag_id, synonym_id, tag_id, synonym_id, tag_id))
                        html +="Synonym'd!"
        html += """<form>Rename <input class="autocomplete" name="tag_name"/> to <input name="new_name"/><input type="submit"/></form>
        <form>Make <input class="autocomplete" name="tag_name"/> a synonym of <input class="autocomplete" name="synonym"/><input type="submit"/></form>"""
        html += footer()
        return html


def header(title="Ponyshack", page_title="Welcome to Ponyshack. This is Ponyshack.", search_box=""):
    web.header("Content-Type", "text/html; charset=UTF-8")
    web.header("Content-Language", "en")
    html = """<!DOCTYPE html>
        <html><head>
            <title>%s</title>
            <link rel="stylesheet" type="text/css" href="/static/rainbowdashalwaysdressesin.css"/>
            <link rel="search" href="/static/opensearch.xml" type="application/opensearchdescription+xml" title="Ponyshack" />
        </head><body><h1 id="title">%s</h1>
        """%(title, page_title)

    html+= """<ul class="button_bar">
        <li><a href="/" class="enormous_button">Home</a></li>
        <li><a href="/all">All</a></li>"""

    if has_alicorn_powers():
        html += """
            <li><a href="/tags">
            Manage tags</a></li>"""

    if has_submit_powers():
        html += """
            <li><a href="/submit" class="enormous_button">
            Submit a picture</a></li>"""

    html += """<li><form id="searchbar" action="/s"><input type="text" class="autocomplete" name="q" value="%s"/>
    </form></li>"""%(search_box,)
    if not (is_logged_in()):
        html += """<li><a class="secret" href="/login">Log in</a></li>"""
    html += "</ul>"
    html += """<div id="page">"""
    return html



def footer():
    return """</div>
        <div id="footer">MLP:FiM &copy; Hasbro, blah blah fair use, this footer is completely pointless</div></body>
        </html>
        <script type="text/javascript" src="/static/script.js"></script>
        """

@dbconnect
def image_link(image_id=None, image_id_36=None, thumbnail=True, extension=True, cursor=None):
    if not image_id and not image_id_36:
        return ""
    elif image_id:
        image_id_36 = web.to36(image_id)
    if extension:
        cursor.execute("""
            SELECT mimetype FROM image WHERE image_id = %s
            """, (image_id or int(image_id_36, 36),))
        mime = cursor.fetchone()[0]
        if mime == "image/png": suffix=".png"
        elif mime == "image/jpeg": suffix=".jpg"
        elif mime == "image/gif": suffix=".gif"
        else: suffix=""

    else:
        suffix=""
    if thumbnail:
        img_url = "/it/"+image_id_36+suffix
    else:
        img_url = "/i/"+image_id_36+suffix
    return """<span class="image"><a href="/i/%s">
        <img alt="image" src="%s"/>
        </a>
        <a href="/view/%s" class="viewlink">More</a>
        </span>"""%(image_id_36+suffix, img_url, image_id_36)

class view:
    @dbconnect
    def GET(self, image_id_36, cursor=None):
        image_id = int(image_id_36, 36)
        webinput = web.input(delete="lol, no", tags=None, rebuild=None, source=None)
        if has_alicorn_powers() and webinput.rebuild:
            cursor.execute("""
                SELECT location, thumb_location, mimetype
                FROM image
                WHERE image_id = %s;
                """,(image_id,))
            image = cursor.fetchone()
            filetype = image[2].upper().split("/")[1]
            make_thumb(image[0], filetype, image[1])
            return header() +\
                """<p>You may have to clear your browser's cache to see the new thumbnail on the rest of the site</p>""" +\
                """<img src="/it/%s?HURPDURP">"""%(image_id_36,) + footer()
        if has_alicorn_powers() and webinput.delete == "DO IT FILLY":
            cursor.execute("""
                SELECT location, thumb_location FROM image
                WHERE image_id = %s;
                """,(image_id,))
            files = cursor.fetchone()
            cursor.execute("""
                SELECT tag_id FROM tag_mapping WHERE image_id=%s
                ;""", (image_id,))
            for tag in cursor:
                rm_tag(tag[0], image_id)
            cursor.execute("""
                DELETE FROM image WHERE image_id = %s;
                SELECT image_id FROM image WHERE location = %s;
                """, (image_id, files[0]))
            if not cursor.fetchone():
                try:
                    os.remove(files[0])
                    os.remove(files[1])
                except OSError:
                    pass
            return header() + "This image has been banished to the moon." + footer()

        if has_submit_powers() and webinput.source:
            source = sanitize_url(webinput.source)
            if source == "":
                source = None
            cursor.execute("""
                UPDATE image SET source = %s
                WHERE image_id = %s;
                """, (source, image_id))


        if has_submit_powers() and webinput.tags:
            cursor.execute("""
                SELECT tag_id FROM tag_mapping WHERE image_id=%s
                ;""", (image_id,))
            for tag in cursor:
                rm_tag(tag[0], image_id)
            tags = webinput.tags.split(",")
            for tag in tags:
                if tag.strip() != "":
                    add_tag(get_tag_id(tag.strip()), image_id)

        cursor.execute("""
            SELECT tag_name FROM
            tag NATURAL INNER JOIN tag_mapping
            WHERE image_id = %s
            ORDER BY tag_name;
            """, (image_id,))
        tags = []
        for tag in cursor:
            tags.append(tag[0])

        cursor.execute("""
            SELECT source FROM image WHERE image_id = %s;
            """, (image_id, ))
        source=cursor.fetchone()[0]

        html = header(title="Ponyshack : Viewing image "+image_id_36, page_title=image_id_36)
        html += """
        <a href="/i/%s"><img src="/i/%s" alt="image"></a><p>Tags : 
        """ % (image_id_36, image_id_36)
        if len(tags) == 0 : html += "none  "
        for tag in tags:
            html += tag_link(tag)+ ", "
        html = html[:-2] + "</p>"

        if source:
            html += """<p>Source : <a class="source-link" href='""" +\
                    source + """'>""" + source + """</a></p>"""


        if has_submit_powers():
            html += """<a href="#" id="edit-link" class="hidden">Edit info</a>"""

            html += """<div class="edit-box">"""

            if not source:
                source = ""
            html += """
            Tags : <form action=""><input type="text" style="width : 350px;" class="autocomplete" name="tags" value="""+'"'
            for tag in tags: html+="%s, "%tag.replace('"', ' ')
            html+='"'+"""/><br>
            Source URL : <input type='text' value='"""+source+"""' name='source'><br>
            <input type="submit" value="Submit"/></form>"""
            if has_alicorn_powers():
                html += """<form><input type="submit" name="rebuild" value="Rebuild thumbnail"/><br>
                <b>DELETE</b>: <input type="submit" name="delete" value="DO IT FILLY"/>
                </form>"""
            html += """</div>"""
        html += footer()
        return html

class login:
    def GET(self):
        return header(page_title="Logging in") + \
                """<form method="POST">
                Username: <input name="user_name"><br>
                Password: <input type="password" name="password"><br>
                <input type="Submit" value="Log in">
                </form>""" + footer()
    @dbconnect
    def POST(self, cursor):
        form = web.input(user_name=None, password=None)
        pass_hash = crypt.crypt(form.password+"baa", "8tr034FhaM4qg")
        cursor.execute("""
            SELECT user_id FROM public.user
            WHERE user_name = %s AND pass_hash = %s
            ;""", (form.user_name, pass_hash))
        user = cursor.fetchone()
        if not user:
            return header(page_title="Logging in") + \
                    """<p><b>Sorry, we couldn't log you in.
                        Did you get your password wrong?</b></p>
                    <form method="POST">
                        Username: <input name="user_name"><br>
                        Password: <input type="password" name="password"><br>
                        <input type="Submit" value="Log in">
                    </form>""" + footer()
        else:
            user_id = user[0]
            auth = random.randint(1, 1000000)
            cursor.execute("""
                UPDATE public.user SET user_auth = %s WHERE user_id = %s;
                """, (auth, user_id))
            cursor.execute("""
                SELECT * FROM public.user WHERE user_id = %s;
                """, (user_id,))
            web.setcookie("user_id", str(user_id), 3600*24*365)
            web.setcookie("auth", str(auth), 3600*24*365)
            web.header("Refresh", "0; /")
            return "Logged in, redirecting"




class submit:
    def GET(self):
        if not has_submit_powers():
            raise web.seeother(domain+"/")
        return header(page_title="Submit a picture") + """
            <form action="/submit" enctype="multipart/form-data" method="POST">
                URL : <input name="url"/> <em>or</em>
                File : <input type="file" name="file"/><br/>
                Tags : <input class="autocomplete" type="text" name="tags"/><br/>
                Source URL : <input type="text" name="source"/> <span class="note">if applicable, eg. deviantart deviation page</span><br/>
                <input type="submit" value="GO GO POWER RANGERS"/>
            </form>
            <h3>Guidelines</h3>
            <ul><li>Please, no NSFW material.</li>
                <li>Try to avoid duplicates</li>
                <li>If the upload doesn't work, try uploading your image
                    to imgur and pasting its url here.</li>
            </ul>
            """ + footer()
    @dbconnect
    def POST(self, cursor=None):
        if not has_submit_powers():
            raise web.seeother(domain+"/")
        form = web.input(file={}, url=None)
        if form["url"]:
            f = urllib.urlopen(form["url"])
            tempfile = "/tmp/"+ str(random.randint(0, 1000))
            out = open(tempfile, "wb")
            data = f.read(1500)
            while data:
                out.write(data)
                data = f.read(1500)
            f.close()
            out.close()
            filename = form["url"]
        else:
            tempfile = "/tmp/"+hashlib.sha1(form["file"].value).hexdigest()
            image = open(tempfile, "wb").write(form["file"].file.read())
            filename = form["file"].filename
        fileformat = os.popen("identify -format %m "+tempfile).read()
        if re.match(r'PNG', fileformat):
            mimetype = "image/png"
            fileformat = "PNG"
        elif re.match(r'(GIF)+', fileformat):
            mimetype = "image/gif"
            fileformat = "GIF"
        elif re.match(r'JPE?G', fileformat):
            mimetype = "image/jpeg"
            fileformat = "JPEG"
        else:
            logging.warning("Attempt to upload "+filename+" from "+web.ctx.ip)
            return "Sorry, we do not accept this format."
        destination = hashlib.sha1(open(tempfile, "rb").read())\
                .hexdigest() + "." + fileformat.lower()
        make_thumb(tempfile, fileformat, thumbsdir + "/" + destination)
        os.rename(tempfile, picsdir + "/" + destination)
        cursor.execute("""
                INSERT INTO image
                (original_filename, location, thumb_location, mimetype, time)
                VALUES (%s, %s, %s, %s, 'now');

                SELECT image_id FROM image WHERE location = %s
                ORDER BY time DESC LIMIT 1;
                """,
            (filename,
                picsdir + "/" + destination,
                thumbsdir + "/" + destination,
                mimetype,
                picsdir+"/"+destination
                ))
        image_id = cursor.fetchone()[0]
        unknown_tags = []
        for tag in form["tags"].split(","):
            tag = tag.strip()
            if tag != "":
                tag_id = get_tag_id(tag.strip())
                add_tag(tag_id, image_id)
        source = sanitize_url(form["source"])
        if source != "":
            cursor.execute("""
                UPDATE image SET source = %s
                WHERE image_id = %s;
                """, (source, image_id))

        return header(page_title="File submitted!") + "<p>" + filename + "<br>" + mimetype + "</p><p><a href='/submit'>&lt;&lt;BACK</a></p>" + footer()

class api_addtag:
    def GET(self):
        w = web.input(i=None, t=None)
        if not (w.i and w.t):
            return "2 WTF YOU DOIN"
        image_id = int(w.i, 36)
        tag_id = w.t
        result = add_tag(tag_id, image_id)
        if result:
            return "0 added"
        else:
            return "1 mapping already exists"

class api_rmtag:
    def GET(self):
        w = web.input(i=None, t=None)
        if not (w.i and w.t):
            return "2 WTF YOU DOIN"
        image_id = int(w.i, 36)
        tag_id = w.t
        result = rm_tag(tag_id, image_id)
        if result:
            return "0 removed"
        else:
            return "1 mapping does not exist"

class api_autocomplete:
    @dbconnect
    def GET(self, cursor=None):
        webinput = web.input(q="", fmt="html")
        tag_partial = webinput.q.split(",")[-1].strip().lower()+"%"
        exclude_tags = webinput.q.split(",")[:-1]
        exclude_tag_ids = [-1, -2]
        for tag in exclude_tags:
            tag_id = get_tag_id(tag, create=False)
            if tag_id:
                exclude_tag_ids.append(tag_id)
        exclude_tag_ids = tuple(exclude_tag_ids)

        cursor.execute("""
            SELECT tag_name, synonym FROM (
                SELECT tag_id, tag_name, synonym
                FROM tag
                WHERE tag_name LIKE %s AND synonym ISNULL
                AND NOT tag_id IN %s

                UNION
                SELECT p.tag_id, t.tag_name, t.synonym
                FROM tag AS t
                INNER JOIN tag AS p ON p.tag_id = t.synonym
                WHERE t.synonym NOTNULL
                AND t.tag_name LIKE %s AND p.tag_name NOT LIKE %s
                AND NOT p.tag_id IN %s
            ) AS tags
            INNER JOIN
            (
                SELECT tag_id, count(*) AS cnt
                FROM tag_mapping
                GROUP BY tag_id
            ) AS tagcounts

            ON tags.tag_id = tagcounts.tag_id
            ORDER BY cnt DESC, tag_name
            LIMIT 8
            """, (tag_partial, exclude_tag_ids, tag_partial, tag_partial, exclude_tag_ids))

        html=""
        json="""["%s",[  """%webinput.q #the two spaces are so the bracket doesn't get deleted if there are no tags
        for tag in cursor:
            tag_name = tag[0]
            if tag[1]:
                synonym_name = get_tag_name(tag[1])
                html += """<li tag_name="%s">%s<span class="synonym">(%s)</span></li>""" % (tag_name,escape(tag_name),escape(synonym_name))
            else:
                html += """<li tag_name="%s">%s</li>""" % (tag_name, escape(tag_name))
            newquery = ",".join(webinput.q.split(",")[:-1]+[tag_name])+", "
            json += """ "%s", """%(newquery.lower())
        json = json[:-2] #remove the trailing comma
        json += """ ]]"""
        html+=""
        if webinput.fmt == "json":
            web.header("Content-Type", "application/json")
            return json
        else:
            return html


urls = (
    "/", "index",
    "/view/([^/]*)", "view",
    "/i/?", "redirect",
    "/it/?", "redirect",
    "/submit/?", "submit",
    #"/i/([^/]*).png", "download",
    #"/i/([^/]*).gif", "download",
    #"/i/([^/]*).jpg", "download",
    "/i/([^/]*)", "download",
    "/it/([^/]*)", "thumbnail",
    "/all", "all",
    "/tags", "tags",
    "/login", "login",
    "/api/autocomplete", "api_autocomplete",
    "/api/addtag", "api_addtag", ###
    "/api/deltag", "api_deltag", ###
    "/s", "search_nojs",
    "/([^/]*)", "search"
    )


if __name__ == "__main__":
    logging.basicConfig(filename="/tmp/ponyshack.log", level=logging.DEBUG) ###
    conn = dbengine.connect(dbparam)
    curs = conn.cursor()
    curs.execute("""
        SELECT count(*) from information_schema.tables
        WHERE table_name IN ('tag', 'image', 'tag_mapping', 'user');
        """)
    count = curs.fetchone()[0]
    if count == 0:
        curs.execute("""
            CREATE TABLE tag (
                tag_id SERIAL PRIMARY KEY,
                tag_name TEXT NOT NULL,
                synonym INTEGER
            );
            CREATE TABLE image (
                image_id SERIAL PRIMARY KEY,
                location TEXT NOT NULL,
                thumb_location TEXT NOT NULL,
                original_filename TEXT,
                mimetype TEXT NOT NULL,
                time TIMESTAMP NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                source TEXT
            );
            CREATE TABLE tag_mapping (
                tag_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL
            ) WITH OIDS;
            CREATE TABLE "user"
            (
                user_id serial NOT NULL,
                user_name text NOT NULL,
                pass_hash text NOT NULL,
                user_auth integer,
                user_type integer NOT NULL DEFAULT 1
            );
            """)
        conn.commit()
        conn.close()
    elif count == 4:
        conn.close()
        web.config.debug = False
        app = web.application(urls, globals())
        app.run()
    else: print("There is something wrong with your tables "
            + str(count))
