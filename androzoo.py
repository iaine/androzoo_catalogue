'''
Processes assocaited with the backend AndroZoo file 
'''
from datetime import datetime
import subprocess
import os
import csv
from multiprocessing import Pool

import requests

from extract_data import extract_data

class AndroZoo():

    def __init__(self):
        #self.apk = apk_name
        #self.store = store
        #self.build_command(apk_name, store, start, end)
        pass

    def _format_clean_apk(self, apk_name):
        '''
          Reformat the name for cli using certain rules. 
        '''
        print(apk_name)
        cleaned_name = apk_name.replace(".", '\.')

        #better way of doing this?
        if not apk_name.strip().endswith('*'):
            cleaned_name += '\"'
        else:
            cleaned_name = apk_name.strip[:-2]


        if not apk_name.strip().startswith('*'):
            cleaned_name = '\"' + cleaned_name
        else:
            cleaned_name = cleaned_name[2:]

        return cleaned_name

    def build_command(self, apk_name, store="", start="", end=""):
        '''
        Build the command using
        App name, store, date start, date end
        '''
        cmd = "/usr/bin/zcat < ../../historical/latest.csv.gz | grep -v ',snaggamea' "

        try:
            if apk_name != "": 
                cleaned_name = self._format_clean_apk(apk_name) 

                cmd += "| awk -F, '{if ($6 ~ /" + cleaned_name +"/) {print} }'"
            elif store != "":
                cleaned_store = store.replace(".", '\.')
                cmd += "| awk -F, '{if ($11 ~ /" + cleaned_store +"/) {print} }'"
            elif start != "":
                cmd += "| awk -F, '{if ( $4 >= \"{0}\" ) {print} }'".format(start)
            elif end != "":
                cmd += "| awk -F, '{if ( $4 <= \"{0}\" ) {print} }'".format(end)
            else:
                raise Exception("Unknown argument")
            print(cmd)
            
        except Exception as e:
            print(e)

        return cmd

    def get_data(self, command, apk):
        '''
        File to process the data
        '''
        fname = self.store(apk=apk)

        #open a subprocess here to create the file
        # remove the first column | cut -d',' -f1 
        try:
            fh = open(fname, 'w')
            fh.close()
            
            subprocess.run(["{} > {}".format(command, fname)], capture_output=True, shell=True)
        except subprocess.CalledProcessError as e:
            print(e)
            os.remove(fname)
        except FileNotFoundError as fe:
            print(fe)
        return fname

    def store(self, apk = ""):
        nowtime = datetime.now().strftime("%Y%m%d-%H%M")
        csv_filename = "{}_{}.csv".format(nowtime, apk)

        return csv_filename

    def collect_apks(self, shalist):
        '''
        Function to download the APKs from AndroZoo

        '''
        try:
            
            with Pool(5) as p:
                p.map(self.process_apk, shalist)
            pass

        except Exception as e:
            print(e)

    def get_shas(self, shalist):
        '''
        Get the shalist from the data
        '''

        shas = subprocess.run("cut -d',' -f1 ./{}".format(shalist))

        return shas

    def download(self, shalist, config):
        '''
        Download the APKs asychronously
        '''

        shas = self.get_shas(shalist)
        print(shas)
        #self.collect_apks(shas)

    def collect_apks(self, apklist):
        '''
         Wrapper to download.
         Needs to create new thread
        '''
        with Pool(5) as pool:
            pool.map(self.process_apk, apklist)
    
    def process_apk(self, sha):
        '''
        Method to download
        '''

        saved_apk = os.path.join("extract", sha)
        API=""
        apk_url = "https://androzoo.uni.lu/api/download?apikey={}&sha256={}".format(API, sha)
        try:
            apk_response = requests.get(apk_url)

            with open(saved_apk, 'wb') as out:
                #catch and log failure
                out.write(apk_response.content)
                
        except Exception as e:
            print(e)

            