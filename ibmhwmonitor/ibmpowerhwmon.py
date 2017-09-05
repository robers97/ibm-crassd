#!/usr/bin/python
'''
#================================================================================
#
#    ibmpowerhwmon.py
#
#    Copyright IBM Corporation 2015-2017. All Rights Reserved
#
#    This program is licensed under the terms of the Eclipse Public License
#    v1.0 as published by the Eclipse Foundation and available at
#    http://www.eclipse.org/legal/epl-v10.html
#
#    U.S. Government Users Restricted Rights:  Use, duplication or disclosure
#    restricted by GSA ADP Schedule Contract with IBM Corp.
#
#================================================================================
'''
import signal, os, sys
import requests
import syslog
import time
import threading
try: 
    import configparser
except ImportError:
    import ConfigParser as configparser
try:
    import Queue as queue
except ImportError:
    import queue
import subprocess
import json

def sigHandler(signum, frame):
    if (signum == signal.SIGTERM):
        print("Termination signal received.")
        errorHandler(syslog.LOG_ERR, "The Power HW Monitoring service has been stopped")  
        sys.exit()
    else:
        print("Signal received" + signum)
        
#setup the interrupt to handle SIGTERM
signal.signal(signal.SIGTERM, sigHandler)
def errorHandler(severity, message):
    print("Creating syslog entry")
    syslog.openlog(ident="IBMPowerHWMonitor", logoption=syslog.LOG_PID|syslog.LOG_NOWAIT)
    syslog.syslog(severity, message)    
      
def OpenBMCEventHandler(openBMCEvent):
    return

def notifyCSM(cerEvent, impactedNode):
    httpHeader = {'Content-Type':'application/json'}
    eventEntry = {'msg_id': "bmc.event." + cerEvent['CerID'], 'location_name':impactedNode}
    try:
        r = requests.post('http://127.0.0.1:5555/csmi/V1.0/ras/event/create', headers=httpHeader, data=json.dumps(eventEntry), timeout=30)
        loginMessage = json.loads(r.text)
        if (loginMessage['status'] != "OK"):
            print(loginMessage["data"]["description"].encode('utf-8')) 
            errorHandler(syslog.LOG_ERR, "Unable to forward HW event")
            return False
        return True
    except(requests.exceptions.Timeout):
        errorHandler(syslog.LOG_ERR, "Connection Timed out connecting to CSM Aggregator. Ensure the service is running")
        return False
    except(requests.exceptions.ConnectionError) as err:
        errorHandler(syslog.LOG_ERR, "Encountered an error connecting to CSM Aggregator. Ensure the service is running. Error: " + str(err))
        return False   
    
def BMCEventProcessor():
    while True:
        node = nodes2poll.get()
        name = threading.currentThread().getName()
        bmcHostname = node['bmcHostname']
        try:
            print(name +": " + bmcHostname)
            if(node['accessType']=="openbmcRest"):
                proc = subprocess.Popen(['python', 'openbmctool.py', '-H', bmcHostname, '-U', 'root', '-P', '0penBmc','-j', 'sel', 'list'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                eventList = proc.communicate()[0]
                eventList = eventList[eventList.index('{'):]
                eventsDict = json.loads(eventList)
            elif(node['accessType']=="ipmi"):
                proc= subprocess.Popen(['java', '-jar', 'ipmiSelParser.jar', bmcHostname, "ADMIN", 'ADMIN'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                eventList = proc.communicate()[0]
                eventList = eventList[eventList.index('{'):]
                eventsDict = json.loads(eventList)
                print("processing alerts")
            else:
                #use redfish
                time.sleep(1)
            
            for i in range(0, len(eventsDict)-2):
                event = "event" +str(i)
                if "error" in eventsDict[event]:
                    errorHandler(syslog.LOG_ERR, "Event not found in lookup table")
                else:
                    #only report new events
                    if(eventsDict[event]['timestamp']>node['lastLogTime']):
                        notifyCSM(eventsDict[event], bmcHostname)
                        node['lastLogTime'] = eventsDict[event]['timestamp']
            nodes2poll.task_done()
        except Exception as e:
            print(e)
        eventsDict.clear()

def initialize():
    #read the config file
    confParser = configparser.ConfigParser()
    try:
        confParser.read('ibmpowerhwmon.config')
        nodes = dict(confParser.items('nodes'))
        for key in nodes:
            mynodelist.append(json.loads(nodes[key]))
    except Exception as e:
        print(e)
    
    #run LSF to verify systems to monitor
    
    
    print("created queue")
    #Create the worker threads
#     for i in range(3):
#         print("Creating thread " + str(i))
#         t = threading.Thread(target=BMCEventProcessor)
#         t.daemon = True
#         t.start()
#     errorHandler(syslog.LOG_INFO, "has been successfully started.")    
    #Setup polling interval
    pollNodes() 

def pollNodes():
    print ("polling the nodes")
    t = threading.Timer(20.0, pollNodes)
    t.daemon = True
    t.start()
    
    
    for i in range (len(mynodelist)):
        nodes2poll.put(mynodelist[i])
    
    
if __name__ == '__main__':
    try:
        nodes2poll = queue.Queue()
        mynodelist = []
        initialize()
#         nodes2poll.join()
        
        print(os.getpid())
        while(True):
#             time.sleep(10)
            if(nodes2poll.empty() == False):
                BMCEventProcessor()
    except KeyboardInterrupt:
        print ("Terminating")