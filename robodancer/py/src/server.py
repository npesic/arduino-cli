import db
import re
from http.server import BaseHTTPRequestHandler,HTTPServer
from os import curdir, sep
import json
import logging
from urllib.parse import urlparse, parse_qs
import json
import robo

PORT_NUMBER = 9081


class myHandler(BaseHTTPRequestHandler):
    abcddb = db.db()
    roboDrive = robo.robo()

    def end_headers (self):
        self.send_header('Access-Control-Allow-Origin', '*')
        BaseHTTPRequestHandler.end_headers(self)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def getExtType(self):
        extType = 'na'
        mimetype = 'text/html'
        if self.path.endswith(".html"):
            mimetype='text/html'
            extType = 'html'
        if self.path.endswith(".jpg"):
            mimetype='image/jpg'
            extType = 'jpg'
        if self.path.endswith(".gif"):
            mimetype='image/gif'
            extType = 'gif'
        if self.path.endswith(".js"):
            mimetype='application/javascript'
            extType = 'js'
        if self.path.endswith(".css"):
            mimetype='text/css'
            extType = 'css'
        if self.path.endswith(".json"):
            mimetype='application/json'
            extType = 'json'
        return {'extType':extType, 'mimeType':mimetype}


    def do_POST(self):
        extType = self.getExtType()
        try:
            content_len = int(self.headers['content-length'])
            post_body = self.rfile.read(content_len)

            self.send_response(200)
            self.send_header('Content-type',extType.get('mimetype'))
            self.end_headers()
            insertRet = self.abcddb.insert(self.path, extType.get('mimetype'), post_body, "public", "group")
            self.wfile.write(bytes(insertRet, "utf-8"))
        except Exception as e:
            logging.exception(e)
            self.send_error(500,'System error on insert: %s' % self.path)

    def do_PUT(self):
        extType = self.getExtType()
        try:
            content_len = int(self.headers['content-length'])
            post_body = self.rfile.read(content_len)

            self.send_response(200)
            self.send_header('Content-type',extType.get('mimetype'))
            self.end_headers()
            updateRet = self.abcddb.update(post_body, 1, "public", "group", self.path)
            self.wfile.write(bytes(updateRet, "utf-8"))
        except Exception as e:
            logging.exception(e)
            self.send_error(500,'System error on update: %s' % self.path)

    def writeJson (self, obj):
        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps(obj, indent=2).encode('utf8'))


    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if self.path.startswith("/robo/"):
            self.roboDrive.dispatch(self.path, params)
            self.writeJson({"path": str(self.path), "status": "Ok"})
            return

        try:
            extType = self.getExtType()

            if self.path.startswith("/fs/get"):
                self.send_response(200)
                self.send_header('Content-type',extType.get('mimetype'))
                self.end_headers()
                self.wfile.write(f.read())
                f.close()

            elif len(params)>0: 
                isFTS = False
                searchStr = '%'
                kwd = '_'
                if 'search' in params:
                    #searchStr = self.path.replace('?search=.*^', '') + params['search'][0]
                    searchStr = re.sub(r'\?search\=.*$', '', self.path) + params['search'][0]
                if 'kwd' in params:
                    kwd = params['kwd'][0]
                    isFTS = True
                author = "public"
                print (searchStr, kwd)
                if isFTS:
                    rec = self.abcddb.fts(searchStr, kwd, author)
                else:
                    rec = self.abcddb.search(searchStr, author)
                if rec is None or len(rec) == 0:
                    self.send_error(404,'File Not Found: %s SearchStr: %s' % (self.path, searchStr))
                    return
                self.send_response(200)
                self.send_header('Content-type','application/json')
                self.end_headers()
                self.wfile.write(json.dumps(rec, indent=2).encode('utf8'))

            else:
                author = "public"
                rec = self.abcddb.get(self.path, author)
                if rec is None or len(rec) == 0:
                    self.send_error(404,'File Not Found: %s' % self.path)
                    return
                self.send_response(200)
                self.send_header('Content-type',extType.get('mimeType'))
                self.end_headers()
                if (type(rec['value']) is str):
                    self.wfile.write(rec['value'].encode('utf8'))
                else:
                    self.wfile.write(rec['value'])


        except IOError:
            self.send_error(404,'File Not Found: %s' % self.path)
        except Exception as e:
            logging.exception(e)
            self.send_error(500,'System error: %s' % self.path)

try:
    server = HTTPServer(('', PORT_NUMBER), myHandler)
    print ('Started httpserver on port ' , PORT_NUMBER)

    server.serve_forever()

except KeyboardInterrupt:
    print ('^C received, shutting down the web server')
    server.socket.close()
