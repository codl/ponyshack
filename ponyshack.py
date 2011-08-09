#!/usr/bin/python2

import web
import re
import os
import subprocess
import logging
import hashlib
import psycopg2


dbengine=psycopg2
dbparam="dbname=ponyshack user=codl"

picsdir = "/tmp/ps"
if not os.path.exists(picsdir):
    os.makedirs(picsdir)
thumbsdir = "/tmp/pst"
if not os.path.exists(thumbsdir):
    os.makedirs(thumbsdir)

def dbconnect(func):
    def newfunc(*args, **kwargs):
        conn = dbengine.connect(dbparam)
        cursor = conn.cursor()
        returnvalue = func(*args, cursor=cursor, **kwargs)
        conn.commit()
        conn.close()
        return returnvalue
    return newfunc

@dbconnect
def get_tag_id(tag, flatten = True, create = True, cursor = None):
    tag = tag.lower().strip()
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



class all:
    @dbconnect
    def GET(self, cursor=None):
        cursor.execute("""
                SELECT image_id FROM image
                ORDER BY views DESC
                ;"""
                );
        images = cursor.fetchall()
        html = header(page_title = "ALL THE THINGS",
                search_box = "all",
                title = "You're killing my bandwidth, but that's okay, I still love you")
        for image in images:
            html += image_link(image_id = image[0])
        html += footer()
        return html

class search:
    @dbconnect
    def GET(self, search, cursor = None):
        taglist = search.split(",")
        temptaglist = []
        for tag in taglist:
            if tag.strip() != "":
                temptaglist.append(get_tag_id(tag.strip()))
        taglist = tuple(temptaglist)
        if taglist == ():
            raise web.seeother("/")
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
        if len(images) == 0 :
            html += "Nothing to see here, sorry"
        else:
            for image in images:
                html += image_link(image_id = image[0])
        return html + footer()

@dbconnect
def tag_link(tag_name = None, tag_id = None, cursor = None):
    if not tag_name and not tag_id: return None
    elif not tag_name:
        cursor.execute("""
            SELECT tag_name FROM tag WHERE tag_id = %s;
            """, (tag_id,))
        tag_name = cursor.fetchone()[0]
    html = "<a href='/%s' class='tag'>%s</a>"%(tag_name,tag_name.replace(" ", "&nbsp;"))
    return html

def has_earth_powers():
    return True ### LOL EVERYONE SUBMITS

def has_pegasus_powers():
    return True ### worst security ever

class index:
    @dbconnect
    def GET(self, cursor = None):
        html = header() + """
        <h3>Most frequent tags</h3><p class="tag_list">"""
        cursor.execute("""
            WITH tag_ids as (
                SELECT tag_id, count(*) count FROM tag_mapping
                GROUP BY tag_id
                )
            SELECT tag_name FROM
            tag_ids NATURAL INNER JOIN tag
            WHERE count > 1
            ORDER BY count DESC LIMIT 20
            ;""")
        for tag in cursor:
            name = tag[0]
            html += tag_link(name) + " "
        html += """</p><h3>Some random tags</h3><p class="tag_list">"""
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
        html += "</p><h3>Most recent images</h3><div class='imageriver'>"
        cursor.execute("""
            select image_id FROM image
            ORDER BY time DESC LIMIT 20
            ;""")
        for image in cursor:
            html += image_link(image_id = image[0])
            #html+="<a href='/i/%s'><img src='/it/%s' alt='this is an image'/></a>"%(web.to36(image[0]),web.to36(image[0]))
        html += "</div>"+footer()
        return html

class download:
    @dbconnect
    def GET(self, imageid, cursor=None):
        imageid = int(imageid, 36)
        cursor.execute("""
            UPDATE image SET views = views+1 WHERE image_id = %s;
            SELECT location, mimetype FROM image
            WHERE image_id = %s
            ;
            """, (imageid, imageid))
        image = cursor.fetchone()
        web.header("Content-Type", image[1])
        return open(image[0], "rb").read()
class thumbnail:
    @dbconnect
    def GET(self, imageid, cursor=None):
        imageid = int(imageid, 36)
        cursor.execute("""
            SELECT thumb_location, mimetype FROM image
            WHERE image_id = %s
            ;
            """, (imageid,))
        image = cursor.fetchone()
        web.header("Content-Type", image[1])
        return open(image[0], "rb").read()

class redirect:
    def GET(self):
        raise web.seeother("/")
class search_nojs:
    def GET(self):
        raise web.seeother("/"+web.input(q="").q)

class tags:
    @dbconnect
    def GET(self, cursor = None):
        if not has_pegasus_powers:
            raise web.seeother("/")
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
    html = """<!DOCTYPE html>
        <html><head>
            <title>%s</title>
            <link rel="stylesheet" type="text/css" href="/static/rainbowdashalwaysdressesin.css"/>
        </head><body><h1 id="title">%s</h1>
        """%(title, page_title)

    html+= """<ul class="button_bar">
        <li><a href="/" class="enormous_button">Home</a></li>
        <li><a href="/all">All</a></li>"""

    if has_pegasus_powers():
        html += """
            <li><a href="/tags">
            Manage tags</a></li>"""

    if has_earth_powers():
        html += """
            <li><a href="/submit" class="enormous_button">
            Submit a picture</a></li>"""

    html += """<li><form id="searchbar" action="/s"><input type="text" class="autocomplete" name="q"/></form></li>"""
    html += "</ul>"
    html += """<div id="page">"""
    return html



def footer():
    return """</div>
        <div id="footer">MLP:FiM &copy; Hasbro, blah blah fair use, this footer is completely pointless</div></body>
        <script type="text/javascript" src="/static/script.js"></script>
        </html>"""

def image_link(image_id=None, image_id_36=None, thumbnail=True):
    if not image_id and not image_id_36:
        return ""
    elif image_id:
        image_id_36 = web.to36(image_id)
    if thumbnail:
        img_url = "/it/"+image_id_36
    else:
        img_url = "/i/"+image_id_36
    return """<span class="image"><a href="/i/%s">
        <img alt="image" src="%s"/>
        </a>
        <a href="/view/%s" class="viewlink">
            <img src="/static/wrench2.png"/>
        </a></span>"""%(image_id_36, img_url, image_id_36)

def message(m):
    return """
    <!DOCTYPE html>
    <html><head><title>Ponyshack</title></head>
    <body><p>%s</p><a href="/">&lt;&lt;HOME</a></body></html>
    """ % m

class view:
    @dbconnect
    def GET(self, image_id_36, cursor=None):
        image_id = int(image_id_36, 36)
        webinput = web.input(delete="lol, no", tags=None)
        if has_pegasus_powers() and webinput.delete == "DO IT FILLY":
            cursor.execute("""
                SELECT location, thumb_location FROM image
                WHERE image_id = %s;
                """,(image_id,))
            files = cursor.fetchone()
            cursor.execute("""
                DELETE FROM image WHERE image_id = %s;
                DELETE FROM tag_mapping WHERE image_id = %s;
                SELECT image_id FROM image WHERE location = %s;
                """, (image_id, image_id, files[0]))
            if not cursor.fetchone():
                os.remove(files[0])
                os.remove(files[1])
            return message("This image has been banished to the moon.")

        if has_pegasus_powers() and webinput.tags:
            cursor.execute("""
                DELETE FROM tag_mapping WHERE image_id = %s;
                """, (image_id,))
            tags = webinput.tags.split(",")
            for tag in tags:
                if tag.strip() != "":
                    cursor.execute("""
                        INSERT INTO tag_mapping (image_id, tag_id)
                        VALUES (%s, %s);
                        """, (image_id, get_tag_id(tag.strip())))

        cursor.execute("""
            SELECT views, time, original_filename FROM image
            WHERE image_id = %s;
            """, (image_id,))
        image = cursor.fetchone()
        cursor.execute("""
            SELECT tag_name FROM
            tag NATURAL INNER JOIN tag_mapping
            WHERE image_id = %s
            ORDER BY tag_name;
            """, (image_id,))
        tags = []
        for tag in cursor:
            tags.append(tag[0])
        html = header(title="Viewing an image on Ponyshack", page_title=image_id_36)
        html += """
        <a href="/i/%s"><img src="/i/%s" alt="image"></a><p>Tags : 
        """ % (image_id_36, image_id_36)
        if len(tags) == 0 : html += "none"
        for tag in tags:
            html += tag_link(tag)+ ", "
        html = html[:-2]
        html += """</p><p>%s</p><p>%s views since %s</p>"""%(image[2], image[0], image[1])
        if has_pegasus_powers():
            html += """<h4>administration thing until I am bothered to CSS + javascript the shit out of this.</h4>
            <form action=""><input type="text" class="autocomplete" name="tags" value='"""
            for tag in tags: html+="%s, "%tag
            html+="""'/><input type="submit" value="gargle!"/><br>
            <b>DELETE</b>: <input type="submit" name="delete" value="DO IT FILLY"/>
            </form>"""
        html += footer()
        return html

class submit:
    def GET(self):
        if not has_earth_powers():
            raise web.seeother("/") ### should be a "suggest an image page"
        return header(page_title="Submit an image") + """
            <form action="/submit" enctype="multipart/form-data" method="POST">
                File : <input type="file" name="file"/><br/>
                Tags : <input class="autocomplete" type="text" name="tags"/><br/>
                <input type="submit" value="GO GO POWER RANGERS"/>
            </form>
            """ + footer()
    @dbconnect
    def POST(self, cursor=None):
        if not has_earth_powers():
            raise web.seeother("/") ### should be a "suggest an image page"
        form = web.input(file={})
        tempfile = "/tmp/"+hashlib.sha1(form["file"].value).hexdigest()
        image = open(tempfile, "wb").write(form["file"].file.read())
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
            logging.warning("Attempt to upload "+form["file"].filename+" from "+web.ctx.ip)
            return "Sorry, we do not accept this format."
        destination = hashlib.sha1(form["file"].value)\
                .hexdigest() + "." + fileformat.lower()
        if fileformat == "GIF":
            # Fixes broken resized gifs
            args = "convert %s -coalesce %s"%(tempfile, tempfile)
            subprocess.call(args.split())
        args = "convert %s -resize x150 %s"%(tempfile,thumbsdir+
                "/"+destination)
        subprocess.call(args.split())
        os.rename(tempfile, picsdir + "/" + destination)
        cursor.execute("""
                INSERT INTO image
                (original_filename, location, thumb_location, mimetype, time)
                VALUES (%s, %s, %s, %s, 'now');

                SELECT image_id FROM image WHERE location = %s
                LIMIT 1;
                """,
            (form["file"].filename,
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
                cursor.execute("""
                        INSERT INTO tag_mapping (tag_id, image_id)
                        VALUES (%s, %s);""", (tag_id, image_id))



        return header(page_title="File submitted!") + "<p>" + form["file"].filename + "<br>" + mimetype + "</p><p><a href='/submit'>&lt;&lt;BACK</a></p>" + footer()

class derp:
    def GET(*args, **kwargs):
        return "DERP"

class api_autocomplete:
    @dbconnect
    def GET(self, cursor=None):
        webinput = web.input(q="")
        tag_partial = webinput.q.split(",")[-1].strip()
        cursor.execute("""
            SELECT tag_name, synonym FROM (
                SELECT tag_id, tag_name, synonym
                FROM tag
                WHERE tag_name LIKE %s AND synonym ISNULL

                UNION
                SELECT p.tag_id, t.tag_name, t.synonym
                FROM tag AS t
                INNER JOIN tag AS p ON p.tag_id = t.synonym
                WHERE t.synonym NOTNULL AND t.tag_name LIKE %s and p.tag_name NOT LIKE %s
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
            """, (tag_partial + "%",)*3)
        html=""
        for tag in cursor:
            tag_name = tag[0]
            if tag[1]:
                synonym_name = get_tag_name(tag[1])
                html += """<li tag_name="%s">%s<span class="synonym">(%s)</span></li>""" % (tag_name,tag_name,synonym_name)
            else:
                html += """<li tag_name="%s">%s</li>""" % (tag_name, tag_name)
        html+=""
        return html


urls = (
    "/", "index",
    "/favicon.ico", "derp", ###
    "/view/([^/]*)", "view",
    "/i/?", "redirect",
    "/it/?", "redirect",
    "/submit/?", "submit",
    "/i/([^/]*)", "download",
    "/it/([^/]*)", "thumbnail",
    "/all", "all",
    "/tags", "tags",
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
        WHERE table_name IN ('tag', 'image', 'tag_mapping');
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
                views INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE tag_mapping (
                tag_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL
            ) WITH OIDS;
            """)
        conn.commit()
        conn.close()
    elif count == 3:
        conn.close()
        app = web.application(urls, globals())
        app.run()
    else: print("There is something wrong with your tables "
            + str(count))
