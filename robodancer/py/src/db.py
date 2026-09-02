import sqlite3
import config
import json
import logging

class db:
    conn = None
    table_name = 'abcd'
    log_table = 'log'
    config = config.config()

    def __init__ (self):
        self.conn = self.connect(self.config.sqlite_file)
        self.createDbObjectsIfNeeded ()
        try:
            info = {}
            info['ip'] = self.config.ip
            info['callsign'] = self.config.callsign
            info['region'] = 'robo-central'
            self.insert('/info.json', 'json', json.dumps(info), 'system', 'public')
            self.update(json.dumps(info), 1, 'system', 'public', '/info.json')
        except Exception:
            print('Failed to update info')
        logging.info ('init done')

    def connect (self, sqlite_file):
        return sqlite3.connect(sqlite_file)

    def createDbObjectsIfNeeded (self):
        c = self.conn.cursor()

        c.execute('CREATE TABLE IF NOT EXISTS {tn} ({path} {path_type}, type TEXT, value TEXT, counter INTEGER, author TEXT, public TEXT)'\
        .format(tn=self.table_name, path="path", path_type="TEXT"))

        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS PathUniqueIndex ON {tn} ({path})'\
        .format(tn=self.table_name, path="path"))

        c.execute('CREATE VIRTUAL TABLE IF NOT EXISTS {tn} USING fts5(path, type, value, counter, author, public, date, method)'\
        .format(tn=self.log_table))

        self.conn.commit()

    def insert (self, path, extType, value, author, group):
        try:
            c = self.conn.cursor()
            c.execute("INSERT INTO {tn} VALUES (?,?,?,?,?,?)"\
            .format(tn=self.table_name), (path, extType, value, 0, author, group))
            self.conn.commit()
            c.execute("INSERT INTO {tn} VALUES (?,?,?,?,?,?,datetime('now'),'POST')"\
            .format(tn=self.log_table), (path, extType, value, 0, author, group))
            return 'OK inserted'
        except sqlite3.IntegrityError:
            return 'ERROR: ID already exists in PRIMARY KEY column {key}'.format(key=path)

    def update (self, value, cnt, author, group, path):
        try:
            extType = 'html'
            c = self.conn.cursor()
            c.execute("UPDATE {tn} SET value=?, counter = ?, author = ?, public =? WHERE path = ?"\
            .format(tn=self.table_name), ( value, cnt, author, group, path))
            c.execute("INSERT INTO {tn} VALUES (?,?,?,?,?,?,datetime('now'),'PUT')"\
            .format(tn=self.log_table), (path, extType, value, 0, author, group))
            self.conn.commit()
            return 'OK: updated'.format(value=path)
        except sqlite3.IntegrityError:
            return 'ERROR: On update for KEY column {key}'.format(key=path)


    def fts (self, path, kwd, author):
        try:
            c = self.conn.cursor()
            c.execute("SELECT path, type, value, counter, author, public FROM {tn} WHERE value match ? and (author = ? or public = 'public') and path like ?"\
            .format(tn=self.log_table), (kwd, author, path))
            records = c.fetchall()
            res=[]
            for row in records:
                ret={}
                if (row is not None):
                    ret['path']=row[0]
                    ret['type']=row[1]
                    ret['counter']=row[3]
                    ret['author']=row[4]
                    ret['public']=row[5]
                    res.append(ret)
            return res
        except sqlite3.IntegrityError:
            return 'ERROR: On get with key={key}'.format(key=path)
        except Exception as e:
            logging.exception(e)
            return 'ERROR: On get with key={key}'.format(key=path)
            

    def search (self, path, author):
        try:
            c = self.conn.cursor()
            c.execute("SELECT path, type, value, counter, author, public FROM {tn} WHERE path like ? and (author = ? or public = 'public')"\
            .format(tn=self.table_name), (path, author))
            records = c.fetchall()
            res=[]
            for row in records:
                ret={}
                if (row is not None):
                    ret['path']=row[0]
                    ret['type']=row[1]
                    ret['counter']=row[3]
                    ret['author']=row[4]
                    ret['public']=row[5]
                    res.append(ret)
            return res
        except sqlite3.IntegrityError:
            return 'ERROR: On get with key={key}'.format(key=path)
        except Exception as e:
            logging.exception(e)
            return 'ERROR: On get with key={key}'.format(key=path)
            

    def get (self, path, author):
        try:
            c = self.conn.cursor()
            c.execute("SELECT path, type, value, counter, author, public FROM {tn} WHERE path = ? and (author = ? or public = 'public')"\
            .format(tn=self.table_name), (path, author))
            row=c.fetchone()
            ret={}
            if (row is not None):
                ret['path']=row[0]
                ret['type']=row[1]
                ret['value']=row[2]
                ret['counter']=row[3]
                ret['author']=row[4]
                ret['public']=row[5]
            return ret
        except sqlite3.IntegrityError:
            return 'ERROR: On get with key={key}'.format(key=path)
        except Exception as e:
            logging.exception(e)
            return 'ERROR: On get with key={key}'.format(key=path)
            
