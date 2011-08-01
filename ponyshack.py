#!/usr/bin/python2

import web
import pylibmc
import logging
import hashlib
import psycopg2


dbengine=psycopg2
dbparam="dbname=ponyshack user=codl"

def dbconnect(func):
    def newfunc(*args, **kwargs):
        conn = dbengine.connect(dbparam)
        cursor = conn.cursor()
        returnvalue = func(*args, cursor=cursor, **kwargs)
        conn.commit()
        conn.close()
        return returnvalue
    return newfunc

### Pointless memcached
#
_mc = pylibmc.Client(["127.0.0.1"], binary=True)
_mcpool = pylibmc.ThreadMappedPool(_mc)

def mcget(key):
    with _mcpool.reserve() as mc:
        return mc.get(key)

def mcset(key, value, time=None):
    with _mcpool.reserve() as mc:
        if time != None:
            return mc.set(key, value, time)
        else:
            return mc.set(key, value)

def cache(func):
    prefix=func.__name__
    def cached(*args, **kwargs):
        ###queryhash=hashlib.md5(prefix+repr(args)+repr(kwargs)).hexdigest()
        queryhash=prefix+repr(args)+repr(kwargs)
        logging.debug('Getting '+queryhash+" from memcached")
        with _mcpool.reserve() as mc:
            data = mc.get(queryhash)
            if data == None:
                logging.debug("Not found")
                data = func(*args, **kwargs)
                mc.set(queryhash, data, 120)
        logging.debug(queryhash+": "+repr(data)[:150])
        return data
    return cached
#
###

@dbconnect
def tag_id(tag, cursor = None):
    """Returns a tag's synonym's id if it has one, else returns the tag's id"""
    cursor.execute("SELECT synonym,tag_id FROM tag WHERE name = %s", (tag,))
    result = cursor.fetchone()
    if result:
        return result[0] if result[0] else result[1]
    else:
        return None

class search:
    @dbconnect
    def GET(self, search, page = 0, cursor = None):
        page = int(page)
        taglist = search.split(",")
        temptaglist = []
        for tag in taglist:
            temptaglist.append(tag_id(tag.strip()))
        taglist = tuple(temptaglist)
        logging.debug("Searching for "+str(taglist))
        cursor.execute("""
                WITH matching as (
                    SELECT image_id FROM tag_mapping
                    WHERE tag_id IN %s
                    GROUP BY image_id HAVING count(*) = %s
                )
                SELECT image_id, location, views FROM
                matching NATURAL INNER JOIN image
                ORDER BY views DESC
                LIMIT 30 OFFSET %s
                ;""",
                (taglist, len(taglist), page*30));
        images = cursor.fetchall()
        if len(images) == 0 :
            return "ABORT! ABORT!" ###
        else:
            html = "<title>PONYSHACK, LOL</title>"
            for image in images:
                html += "<a href='/i/%s'>"%image[0] + image[1] + "</a>, <a href='/view/%s'>"%image[0] + str(image[2]) + " views</a>" + "<br/>"
            return html

class index:
    @dbconnect
    def GET(self, cursor = None):
        cursor.execute("""
            select image_id, location FROM image
            ORDER BY time DESC LIMIT 10
            ;""")
        html = "<title>PONYSHACK, LOL</title><h3>Most recent images</h3><ul>"
        for image in cursor:
            html+="<li>"+image[1]+"</li>"
        html += "</ul><h3>Most frequent tags</h3><ul>"
        cursor.execute("""
            WITH tag_ids as (
                SELECT tag_id, count(*) count FROM tag_mapping
                GROUP BY tag_id
                )
            SELECT name FROM
            tag_ids NATURAL INNER JOIN tag
            ORDER BY count DESC LIMIT 15
            ;""")
        for tag in cursor:
            name = tag[0]
            html += "<li><a href='/%s'>%s</a></li>"%(name,name)
        html += "</ul>"
        return html


class derp:
    def GET(*args):
        return "DERP"



urls = (
    "/", "index",
    "/view/([^/]*)", "view",
    "/i/([^/]*)", "download",
    "/it/([^/]*)", "thumbnail",
    "/favicon.ico", "derp", ###
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
                name TEXT NOT NULL,
                synonym INTEGER
            );
            CREATE TABLE image (
                image_id SERIAL PRIMARY KEY,
                location TEXT NOT NULL,
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
