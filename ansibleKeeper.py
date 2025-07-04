#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__     = "Jan Kogut"
__copyright__  = "Jan Kogut"
__license__    = "MIT"
__version__    = "0.0.1"
__maintainer__ = "Jan Kogut"
__status__     = "Beta"


import json
import toml
import configparser
from optparse import OptionParser,OptionGroup
from kazoo.client import KazooClient



## START of config section
##################################################

class OurConfig(object):
    ''' Our config section '''

    pass

cfg = OurConfig()

cfg.zkServers  = 'con1:2181,con2:2181,con3:2181'
cfg.aPath      = '/ansible-test'

#################################################
## END of config section 


def oParser():
    '''
    Commandline options parsing function.

    Return dict (parsed options).
    '''

    parser = OptionParser(usage="usage: %prog [opts] <args>",
                          version="%prog 0.0.1")
    parser.add_option("-A", nargs = 1,
                      help="add host with hostvars: groupname1:newhostname1,var1:value1,var2:value2,var3:value3\n")
    parser.add_option("-G", nargs = 1,
                      help="add existing host to hostgroup: groupname:hostname")
    parser.add_option("-D", nargs = 1,
                      help="delete host or group recursively: groupname1:hostname1 or groupname1 or hosts:hostname1")
    parser.add_option("-U", nargs = 1,
                      help="update host variables with comma separated hostvars: groupname1:hostname1,var1:newvalue1,var2:newvalue2")
    parser.add_option("-R", nargs = 1,
                      help="rename existing hostname or groupname: groups:oldgroupname:newgroupname or hosts:oldhostname:newhostname")
    parser.add_option("-S", nargs = 1,
                      help="show host variables for a given host or group: groupname1:hostname1 or groupname1")
    parser.add_option("-I", nargs = 1,
                      help="inventory mode: groups|all|ansible dumps inventory in json format from zookeeper")
    parser.add_option("--host", nargs = 1,
                      help="ansible compliant option for hostvars access: --host hostname")
    parser.add_option("--import-toml", nargs=1, help="import inventory from TOML file")
    parser.add_option("--export-toml", nargs=1, help="export inventory to TOML file")
    parser.add_option("--import-ini", nargs=1, help="import inventory from INI file")
    parser.add_option("--export-ini", nargs=1, help="export inventory to INI file")

    group = OptionGroup(parser, "Example usage",
                        "ansibleKeeper.py -A flink:flink-master01,lan_ip:10.1.1.1")
                        
    parser.add_option_group(group)
    
    (opts, args) = parser.parse_args()
    
    
    if (opts.A or opts.G or opts.D or opts.U or opts.R or opts.S or opts.I or opts.host or opts.import_toml or opts.export_toml or opts.import_ini or opts.export_ini) == None:

        parser.print_help()
        exit(-1)
        
    return {'addMode':opts.A, 'groupMode':opts.G, 'deleteMode':opts.D, 'updateMode':opts.U,
            'renameMode':opts.R, 'showMode':opts.S, 'inventoryMode':opts.I, 'ansibleHost':opts.host,
            'importToml': opts.import_toml, 'exportToml': opts.export_toml,
            'importIni': opts.import_ini, 'exportIni': opts.export_ini}


def zkStartRo():
    '''
    Start a zookeeper client connection in read-only mode.

    Return zookeeper read-only connection object.
    '''

    zk = KazooClient(hosts=cfg.zkServers, read_only = True)
    zk.start()
    
    return zk


def zkStartRw():
    '''
    Start a zookeeper client connection in read-write mode.

    Return zookeeper read-write connection object.
    '''

    zk = KazooClient(hosts=cfg.zkServers)
    zk.start()
    
    return zk
    

class ArgError(object):
    ''' Class for handling errors '''

    def __init__(self, tp, format_args):
        self.tp = tp
        self.format_args = format_args

    def format(self):
        return self.tp, self.format_args


class CommonInformer(ArgError):
    ''' Class for message informing '''
    
    pass
                                            
    
def splitZnodeVarString(znodeVarString):
    '''
    Parse string for commandline opts: <-A|-U>.

    Return dict.
    '''

    ## spliting example string into dictionary:
    ## example string: groupname:hostname1,var1:val1,var2:val2,var3:val3
    ## desired dict  : {"groupname":{"hostname1":{"var1":"val1", "var2":"val2", "var3":"val3"}}}

    varList = znodeVarString.split(',')
    varDict = {}

    for var in varList[1:]:
        varDict[var.split(':')[0]] = var.split(':')[1]
       
    groupName, hostName = varList[0].split(':')[0], varList[0].split(':')[1]
    return { groupName : { hostName : varDict }}


def splitZnodeString(znodeString):
    '''
    Splits znodeString into groupName, hostName, groupPath, hostPath, hostGroupPath.

    Return list of tuples or list of tuple.
    '''

    ## spliting example string into list of tuples or list of tuple :
    ## example string: groupname:hostname1
    ## example output: [("groupname","/ansible_zk/groups/groupname"),
    ##                  ("hostname1","/ansible_zk/hosts/hostname1","/ansible_zk/groups/groupname/hostname1")]


    if 'hosts:' in znodeString:
        hostName       = znodeString.split(':')[1]
        hostPath       = "{0}/hosts/{1}".format(cfg.aPath, hostName)
        return [(hostName, hostPath, None)]

    elif ':' in znodeString:
        groupName      = znodeString.split(':')[0]
        hostName       = znodeString.split(':')[1]
        groupPath      = "{0}/groups/{1}".format(cfg.aPath, groupName)
        hostPath       = "{0}/hosts/{1}".format(cfg.aPath, hostName)
        hostGroupPath  = "{0}/{1}".format(groupPath, hostName)
        return [(groupName, groupPath),(hostName, hostPath, hostGroupPath)]

    else:
        groupName = znodeString
        groupPath = "{0}/groups/{1}".format(cfg.aPath, groupName)
        return [(groupName, groupPath)]


def splitRenameZnodeString(renameZnodeString):
    '''
    Splits znodeString into [old|new]GroupName, [old|new]HostName, [old|new]GroupPath, [old|new]HostPath.

    Return list of tuples or ERROR string.
    '''

    ## spliting example string into list of tuples or list of tuple :
    ## example string for newgroupname :  groups:oldgroupname:newgroupname
    ## example string for newhostname  :  hosts:oldhostname:newhostname
    ## example output: [("newgroupname","/ansible_zk/groups/newgroupname"),
    ##                  ("newhostname","/ansible_zk/hosts/newhostname")]

    ERROR_MSGS = {
        'NO_VALID_KEYWORDS_NUMBER':"{0} <-- no valid number of keywords [keyword:keyword1:newkeyword1]".format(renameZnodeString),
        'NO_VALID_KEYWORDS_STRING':"{0} <-- no valid keywords [groups|hosts] found".format(renameZnodeString)
    }

    ## check if len of splited list is not 3
    if len(renameZnodeString.split(':')) != 3:
       return ArgError('NO_VALID_KEYWORDS_NUMBER', ERROR_MSGS['NO_VALID_KEYWORDS_NUMBER']).format()
    
    if 'hosts:' in renameZnodeString:
        oldHostName    = renameZnodeString.split(':')[1]
        newHostName    = renameZnodeString.split(':')[2]

        oldHostPath    = "{0}/hosts/{1}".format(cfg.aPath, oldHostName)
        newHostPath    = "{0}/hosts/{1}".format(cfg.aPath, newHostName)
        return [(oldHostName, oldHostPath), (newHostName, newHostPath)]

    elif 'groups' in renameZnodeString:
        oldGroupName    = renameZnodeString.split(':')[1]
        newGroupName    = renameZnodeString.split(':')[2]

        oldGroupPath    = "{0}/groups/{1}".format(cfg.aPath, oldGroupName)
        newGroupPath    = "{0}/groups/{1}".format(cfg.aPath, newGroupName)
        return [(oldGroupName, oldGroupPath), (newGroupName, newGroupPath)]

    else:
        return ArgError('NO_VALID_KEYWORDS_STRING', ERROR_MSGS['NO_VALID_KEYWORDS_STRING']).format()

    
def addHostWithHostvars(znodeDict):
    '''
    Add existing znode to new group.

    Return string (ADDED    ==> host: hostname to group: groupname).
    '''
  
    zk = zkStartRw()

    groupName      = list(znodeDict.keys())[0]
    hostName       = list(znodeDict[groupName].keys())[0]
    groupPath      = "{0}/groups/{1}".format(cfg.aPath, groupName)
    hostPath       = "{0}/hosts/{1}".format(cfg.aPath, hostName)
    hostGroupPath  = "{0}/{1}".format(groupPath, hostName)

    ERROR_MSGS = {
        'HOST_EXISTS': "host: {0} exists !!!".format(hostName),
        'HOST_EXISTS_IN_GROUP': "host: {0} in group {1} exists !!!".format(hostName, groupName)
    }

    COMMON_MSGS = {
        'ADDED_HOST_TO_GROUP': "ADDED  ==> host: {0} to group: {1}".format(hostName, groupName)
    }

    try:
        if zk.exists(hostPath):
            return ArgError('HOST_EXISTS',ERROR_MSGS['HOST_EXISTS']).format()

        elif zk.exists(hostGroupPath):
            return ArgError('HOST_EXISTS_IN_GROUP',ERROR_MSGS['HOST_EXISTS_IN_GROUP']).format()

        else:
            zk.ensure_path(hostPath)
            zk.ensure_path(hostGroupPath)

            for key in znodeDict[groupName][hostName]:
                varPath = "{0}/{1}".format(hostPath, key)
                varVal  = znodeDict[groupName][hostName][key]
                zk.create(varPath, varVal)

            return CommonInformer('ADDED_HOST_TO_GROUP',COMMON_MSGS['ADDED_HOST_TO_GROUP']).format()

    finally:
        zk.stop()    
    

def addHostToGroup(znodeStringSplited):
    '''
    Add host to group.

    Return string (ADDED  ==> host: hostname to group: groupname).
    '''

    zk = zkStartRw()

    groupName, groupPath              = znodeStringSplited[0]
    hostName, hostPath, hostGroupPath = znodeStringSplited[1]

    ERROR_MSGS = {
        'HOST_EXISTS_IN_GROUP': "ERROR  ==> host: {0} in group {1} exists !!!".format(hostName, groupName),
        'HOST_DOES_NOT_EXIST': "ERROR  ==> host: {0} does not exist !!! Could not add non-existent host: {0} to group: {1}".format(hostName, groupName)
    }

    COMMON_MSGS = {
        'ADDED_HOST_TO_GROUP': "ADDED  ==> host: {0} to group: {1}".format(hostName, groupName)
    }
  
    try:
        if zk.exists(hostGroupPath):
            return ArgError('HOST_EXISTS_IN_GROUP',ERROR_MSGS['HOST_EXISTS_IN_GROUP']).format()

        if zk.exists(hostPath) is None:
            return ArgError('HOST_DOES_NOT_EXIST',ERROR_MSGS['HOST_DOES_NOT_EXIST']).format()
        
        zk.ensure_path(hostGroupPath)
        return CommonInformer('ADDED_HOST_TO_GROUP',COMMON_MSGS['ADDED_HOST_TO_GROUP']).format()

    finally:
        zk.stop()


def deleteZnodeRecur(znodeStringSplited):
    '''
    Delete znode recursivelly for a given string groupname or hosts:hostname or groupname:hostname.

    Return string (DELETED||ERROR  ==> [host: hostname || group: groupname]).
    '''

    zk = zkStartRw()

    try:
        if len(znodeStringSplited) > 1:  ## check if it is <groupname:hostname> case

            groupName, groupPath              = znodeStringSplited[0]
            hostName, hostPath, hostGroupPath = znodeStringSplited[1]

            ERROR_MSGS = {
                'HOST_DOES_NOT_EXIST': "ERROR  ==> could not delete host: {0} that does not exist !!!".format(hostName),
                'HOST_DOES_NOT_EXISTS_IN_GROUP': "ERROR  ==> could not delete host: {0} that does not exist in group: {1} !!!".format(hostName, groupName),
                'GROUP_DOES_NOT_EXIST': "ERROR  ==> could not delete group: {0} that does not exist !!!".format(groupName)
            }

            COMMON_MSGS = {
                'DELETED_HOST_IN_GROUP': "DELETED ==> host: {0} in group: {1}".format(hostName, groupName),
                'DELETED_GROUP': "DELETED ==> group: {0}".format(groupName),
                'DELETED_HOST': "DELETED ==> host: {0}".format(hostName)
                
            }

            
            if zk.exists(hostPath) is None:
                return ArgError('HOST_DOES_NOT_EXIST',ERROR_MSGS['HOST_DOES_NOT_EXIST']).format()

            if zk.exists(hostGroupPath) is None:
                return  ArgError('HOST_DOES_NOT_EXISTS_IN_GROUP',ERROR_MSGS['HOST_DOES_NOT_EXISTS_IN_GROUP']).format()

            if len(zk.get_children(groupPath)) == 1:  ## delete group if there is only one host in it
                zk.delete(groupPath, recursive=True)

            else:
                zk.delete(hostGroupPath, recursive=True)
                return CommonInformer('DELETED_HOST_IN_GROUP',ERROR_MSGS['DELETED_HOST_IN_GROUP']).format()
    
        elif len(znodeStringSplited) == 1:  ## check if it is <groupname> or <hosts:hostname> case    
            if len(znodeStringSplited[0]) == 2:  ## first check for group only
        
                groupName, groupPath = znodeStringSplited[0]
       
                if zk.exists(groupPath) is None:
                    return ArgError('GROUP_DOES_NOT_EXIST',ERROR_MSGS['GROUP_DOES_NOT_EXIST']).format()

                else:
                    zk.delete(groupPath, recursive=True)
                    return CommonInformer('DELETED_GROUP',ERROR_MSGS['DELETED_GROUP']).format()
            
            else:  ## then assume check for hosts only 

                hostName, hostPath, notUsedValue = znodeStringSplited[0]
                
                if zk.exists(hostPath) is None:
                    return ArgError('HOST_DOES_NOT_EXIST',ERROR_MSGS['HOST_DOES_NOT_EXIST']).format()

                else:
                    zk.delete(hostPath, recursive=True)
                    return CommonInformer('DELETED_HOST',ERROR_MSGS['DELETED_HOST']).format()
            
        else:  ## Unknown cases        
            return "ERROR with processing znodeStrings !!!"           

    finally:
        zk.stop()


def updateZnode(znodeDict):
    '''
    Update znode with hostvars.

    Return string (ERROR ... || UPDATED ... || NOT UPDATED ...).
    '''


    # COMMON_MSGS = {
    #     'DELETED_HOST_IN_GROUP': "DELETED ==> host: {0} in group: {1}".format(hostName, groupName),
    #     'DELETED_GROUP': "DELETED ==> group: {0}".format(groupName),
    #     'DELETED_HOST': "DELETED ==> host: {0}".format(hostName)

    # }

    
    zk = zkStartRw()
    
    groupName   = list(znodeDict.keys())[0]
    hostName    = list(znodeDict[groupName].keys())[0]
    hostPath    = "{0}/hosts/{1}".format(cfg.aPath, hostName)
    hostVarList = zk.get_children(hostPath)

    ERROR_MSGS = {
        'HOST_DOES_NOT_EXIST': "ERROR  ==> could not update host: {0} that does not exist !!!".format(hostName)
        # 'HOST_DOES_NOT_EXISTS_IN_GROUP': "ERROR  ==> could not delete host: {0} that does not exist in group: {1} !!!".format(hostName, groupName),
        # 'GROUP_DOES_NOT_EXIST': "ERROR  ==> could not delete group: {0} that does not exist !!!".format(groupName)
    }

    
    try:
        if zk.exists(hostPath) is None:
#            return ArgError('HOST_DOES_NOT_EXIST',ERROR_MSGS['HOST_DOES_NOT_EXIST']).format()
            return "ERROR  ==> could not update host: {0} that does not exist !!!".format(hostName)

        for hostVar in hostVarList:
            if zk.exists("{0}/{1}".format(hostPath, hostVar)) is None: 
                return "ERROR  ==> hostvar: {0} for host {1} does not exist !!!".format(hostVar, hostName)

        nonExistList = []    
        updatedDict  = {}
    
        for var in znodeDict[groupName][hostName]:
            varPath = "{0}/{1}".format(hostPath, var)
            varVal  = znodeDict[groupName][hostName][var]
        
            if var in hostVarList: ## check if given variable exists
                zk.set(varPath, varVal)
                updatedDict[var] = varVal
            
            else:
                nonExistList.append(var)
           
        if len(nonExistList) > 0 and len(updatedDict) == 0:
            return "NOT UPDATED  ==> host: {0} with no existing hostvars {1} ===> NOT UPDATED hostvars {2} which do not exist".format(hostName, updatedDict, nonExistList)

        elif len(nonExistList) and len(updatedDict) > 0:
            return "UPDATED  ==> host: {0} with new hostvars {1} ===> NOT UPDATED hostvars {2} which do not exist".format(hostName, updatedDict, nonExistList)
    
        else:
            return "UPDATED  ==> host: {0} with new hostvars {1}".format(hostName, updatedDict)

    finally:
        zk.stop()    
        
        
def renameZnode(znodeRenameStringSplited):
    '''
    Rename znode for a given tuple of ((oldName, oldPath), (newName, newPath)).

    Return string (ERROR ... || RENAMED ... || NOT RENAMED ...).
    '''
    
    zk = zkStartRw()

    oldName, oldPath  = znodeRenameStringSplited[0]
    newName, newPath  = znodeRenameStringSplited[1]
    
    def renameHostInGroup(oldName, newName):
        '''
        Find a corresponding group in groups for oldName, rename host with newName
        and delete that host.

        Return string (ERROR ...||RENAMED ...).
        '''

        ## find a group where host resides and create newPath in that group
        for child in zk.get_children('{}/groups'.format(cfg.aPath)):
            if oldName in zk.get_children('{0}/groups/{1}'.format(cfg.aPath, child)):
                print(('found ==> {0}/groups/{1}/{2}'.format(cfg.aPath, child, oldName)))
                tmpOldHostGroupPath = '{0}/groups/{1}/{2}'.format(cfg.aPath, child, oldName)
                tmpNewHostGroupPath = '{0}/groups/{1}/{2}'.format(cfg.aPath, child, newName)
                zk.ensure_path(tmpNewHostGroupPath)
                        
                ## delete oldPath from groups/group_to_find/host     
                zk.delete(tmpOldHostGroupPath)
                return "RENAMED host {0} in group {1} --> {2}".format(oldName, child, newName)

            else:
                return "ERROR ---> NO GROUP FOUND !!!"

    try:
        if zk.exists(oldPath) is None:
            return "ERROR  ==> could not rename nonexistent path: {0} !!!".format(oldPath)

        if zk.exists(newPath) is not None:
            return "ERROR  ==> new path already exist: {0} !!!".format(newPath)
    
        ## rename only when newPath does not exist
        if zk.exists(newPath) is None:
            if 'hosts' in oldPath:
                ## check for hostvars, if none create newPath and delete oldPath
                if len(zk.get_children(oldPath)) == 0:
                    zk.ensure_path(newPath)
                
                    ## find, rename and delete host with no hostvars in a corresponding group
                    renameHostInGroup(oldName, newName)
                    zk.delete(oldPath)
                    return "RENAMED {0} --> {1}".format(oldName, newName)

                else:
                    ## create newPath in hosts copy hostvars from oldPath 
                    varDict = {}
                    for child in zk.get_children(oldPath):
                        varDict[child] = zk.get('{0}/{1}'.format(oldPath,child))[0]
                    
                    zk.ensure_path(newPath)
                    for var in varDict:
                        zk.create('{0}/{1}'.format(newPath,var),varDict[var])

                    ## find, rename and delete host with no hostvars in a corresponding group
                    renameHostInGroup(oldName, newName)

                    ## delete oldPath from hosts
                    zk.delete(oldPath, recursive=True)
                    return "RENAMED {0} --> {1}".format(oldName, newName)

            elif 'groups' in oldPath:
            ## look for hosts in the group, create new group
            ## delete theirs znode in that group ONLY and create new ones in the group

                oldChildren = zk.get_children(oldPath)
                zk.ensure_path(newPath)

                for child in oldChildren:
                    zk.ensure_path('{0}/{1}'.format(newPath, child))

                ## delete old group with its members
                zk.delete(oldPath, recursive=True)
                return "RENAMED group {0} --> {1}".format(oldName, newName)

            else:
                return "ERROR no valid keywords <groups|hosts> found"

    finally:
        zk.stop()
            
            
def showHostVars(znodeStringSplited):
    '''
    Show hostvars for a given hosts:hostname or groupname.
    
    Return dict or string (in case of ERROR).
    '''

    zk = zkStartRo()

    try:
        if len(znodeStringSplited[0]) == 2:    ## check for groupname only

            groupName, groupPath = znodeStringSplited[0]

            if zk.exists(groupPath) is None:
                return "ERROR  ==> no such groupname: {0} !!!".format(groupName)

            else:
                hostList    = zk.get_children(groupPath)
                varDict     = {}

                for host in hostList:             ## build a dict with host variables
                    tmpHostPath    = "{0}/hosts/{1}".format(cfg.aPath, host)
                    varDict[host]  = zk.get_children('{0}'.format(tmpHostPath))

                    valDict = {}
                    for var in varDict[host]:
                        valDict[var] = zk.get('{0}/{1}'.format(tmpHostPath, var))[0]

                    varDict[host] = valDict
                return varDict
                    
        elif len(znodeStringSplited[0]) == 3:     ## check for hostname only   

            hostName, hostPath, notUsedValue =  znodeStringSplited[0]

            if zk.exists(hostPath) is None:
                return "ERROR  ==> no such host: {0} !!!".format(hostName)

            else:
                varDict  = {}
                varDict[hostName]  = zk.get_children('{0}'.format(hostPath))

                valDict = {}
                for var in varDict[hostName]:
                    valDict[var]  = zk.get('{0}/{1}'.format(hostPath, var))[0]

                varDict[hostName] = valDict
                return varDict

        else:
            return "ERROR with processing znodeStrings !!!"

    finally:
        zk.stop()


def inventoryDump(dumpMode):
    '''
    User friendly inventory dump for all|groups modes.
    
    Return dict or list.
    '''

    zk = zkStartRo()

    # from ipdb import set_trace; set_trace()
    hostsList  = sorted(zk.get_children("{}/hosts".format(cfg.aPath)))
    groupsList = sorted(zk.get_children("{}/groups".format(cfg.aPath)))
    dumpDict   = {"hosts": hostsList}

    tmpList = []

    try:
        if dumpMode == 'hosts':
            return hostsList

        elif dumpMode == 'groups':
            return groupsList

        elif dumpMode == 'all':
            for group in groupsList:
                tmpDict  = {}
                path     = "{0}/groups/{1}".format(cfg.aPath, group)
                children = sorted(zk.get_children(path))
                tmpDict[group] = children
                tmpList.append(tmpDict)
                
                dumpDict["groups"] = tmpList

            return dumpDict

    finally:
        zk.stop()


def ansibleInventoryDump():
    '''
    Ansible compliant inventory dump for a given list of zookeeper servers and ansible-keeper path.
    
    Return dict.
    '''

    ## The stock inventory script system detailed above works for all versions of Ansible, but calling --host for
    ## every host can be rather expensive, especially if it involves expensive API calls to a remote subsystem.
    ## In Ansible 1.3 or later, if the inventory script returns a top level element called “_meta”,
    ## it is possible to return all of the host variables in one inventory script call. When this meta element
    ## contains a value for “hostvars”, the inventory script will not be invoked with --host for each host.
    ## This results in a significant performance increase for large numbers of hosts, and also makes client side
    ## caching easier to implement for the inventory script.
    ##
    ## Source: http://docs.ansible.com/ansible/dev_guide/developing_inventory.html#tuning-the-external-inventory-script

    zk = zkStartRo()

    groupList = zk.get_children("{}/groups".format(cfg.aPath))
    groupDict = {}
    
    for group in groupList:
        path     = "{0}/groups/{1}".format(cfg.aPath, group)
        children = zk.get_children(path)
        tmpDict  = {}
        tmpDict['hosts'] = children
        tmpDict['vars']  = {} ## not yet implemented
        groupDict[group] = tmpDict
        
    ## building ansible compliant hostvars dict:
    ##
    ## {"_meta": {
    ##     "hostvars": {
    ##         "moocow.example.com": {"asdf" : 1234, "var2": 111 },
    ##         "llama.example.com": {"asdf": 5678, "var2": 222 }
    ##     }
    ## }}

    hostList    = zk.get_children("{}/hosts".format(cfg.aPath))
    hostVarDict = {}
    varDict     = {}

    for host in hostList:             ## build a dict with host variables
        tmpHostPath    = "{0}/hosts/{1}".format(cfg.aPath, host)
        varDict[host]  = zk.get_children('{0}'.format(tmpHostPath))

        valDict = {}
        for var in varDict[host]:
            valDict[var] = zk.get('{0}/{1}'.format(tmpHostPath, var))[0]

        varDict[host] = valDict

    ## modify output dict to be compliant with ansible >= 1.3 version
    hostVarDict['hostvars'] = varDict
    groupDict['_meta']      = hostVarDict
    
    zk.stop()
    return groupDict


def ansibleHostAccess(hostName):
    '''
    Ansible pre 1.3 compliant hostvars dump.

    Return dict.
    '''

    ## Before version 1.0, each group could only have a list of hostnames/IP addresses, like the webservers,
    ## marietta, and 5points groups above.
    ##
    ## When called with the arguments --host <hostname> (where <hostname> is a host from above), the script
    ## must print either an empty JSON hash/dictionary, or a hash/dictionary of variables to make available
    ## to templates and playbooks. Printing variables is optional, if the script does not wish to do this,
    ## printing an empty hash/dictionary is the way to go
    ##
    ## Source: http://docs.ansible.com/ansible/dev_guide/developing_inventory.html#script-conventions
    
    zk = zkStartRo()

    hostPath = "{0}/hosts/{1}".format(cfg.aPath, hostName)

    try:
        if zk.exists(hostPath) is None:
            return "ERROR  ==> no such host: {0} !!!".format(hostName)

        else:
            varList = zk.get_children('{0}'.format(hostPath))
      
            varDict = {}
            for var in varList:
                varDict[var]  = zk.get('{0}/{1}'.format(hostPath, var))[0]

            return varDict

    finally:
        zk.stop()   
        
    
def exportToToml(filePath):
    '''
    Export inventory to TOML file.
    '''
    inventory = ansibleInventoryDump()
    with open(filePath, 'w') as f:
        toml.dump(inventory, f)
    return "Exported inventory to {}".format(filePath)

def importFromToml(filePath):
    '''
    Import inventory from TOML file.
    '''
    try:
        with open(filePath, 'r') as f:
            inventory = toml.load(f)
    except (IOError, toml.TomlDecodeError) as e:
        return "Error reading TOML file: {}".format(e)

    zk = zkStartRw()
    try:
        for group, data in inventory.items():
            if group == '_meta':
                continue
            
            groupPath = "{}/groups/{}".format(cfg.aPath, group)
            zk.ensure_path(groupPath)

            for host in data.get('hosts', []):
                hostPath = "{}/hosts/{}".format(cfg.aPath, host)
                zk.ensure_path(hostPath)
                
                hostGroupPath = "{}/{}".format(groupPath, host)
                zk.ensure_path(hostGroupPath)

                if '_meta' in inventory and 'hostvars' in inventory['_meta']:
                    hostvars = inventory['_meta']['hostvars'].get(host, {})
                    for var, val in hostvars.items():
                        varPath = "{}/{}".format(hostPath, var)
                        zk.create(varPath, str(val).encode('utf-8'), makepath=True)

    finally:
        zk.stop()
    return "Imported inventory from {}".format(filePath)


def exportToIni(filePath):
    '''
    Export inventory to INI file.
    '''
    inventory = ansibleInventoryDump()
    config = configparser.ConfigParser(allow_no_value=True)

    for group, data in inventory.items():
        if group == '_meta':
            continue
        
        config.add_section(group)
        for host in data.get('hosts', []):
            config.set(group, host, None)

    if '_meta' in inventory and 'hostvars' in inventory['_meta']:
        for host, hostvars in inventory['_meta']['hostvars'].items():
            section_name = "hostvars:{}".format(host)
            config.add_section(section_name)
            for var, val in hostvars.items():
                config.set(section_name, var, val)

    with open(filePath, 'w') as f:
        config.write(f)
    return "Exported inventory to {}".format(filePath)

def importFromIni(filePath):
    '''
    Import inventory from INI file.
    '''
    config = configparser.ConfigParser(allow_no_value=True)
    try:
        config.read(filePath)
    except (IOError, configparser.Error) as e:
        return "Error reading INI file: {}".format(e)

    zk = zkStartRw()
    try:
        for section in config.sections():
            if section.startswith('hostvars:'):
                continue

            group = section
            groupPath = "{}/groups/{}".format(cfg.aPath, group)
            zk.ensure_path(groupPath)

            for host in config.options(section):
                hostPath = "{}/hosts/{}".format(cfg.aPath, host)
                zk.ensure_path(hostPath)
                
                hostGroupPath = "{}/{}".format(groupPath, host)
                zk.ensure_path(hostGroupPath)

                hostvars_section = "hostvars:{}".format(host)
                if config.has_section(hostvars_section):
                    for var, val in config.items(hostvars_section):
                        varPath = "{}/{}".format(hostPath, var)
                        zk.create(varPath, str(val).encode('utf-8'), makepath=True)
    finally:
        zk.stop()
    return "Imported inventory from {}".format(filePath)
    
def main():
    '''
    Main logic
    '''

    zk  = zkStartRw()
    try:
        assert type(zk).__name__ == 'KazooClient'

    finally:
        zk.stop()

   
    ## options for ansible only 
    if oParser()['ansibleHost'] is not None:
        print(json.dumps(ansibleHostAccess(oParser()['ansibleHost'])))

    if oParser()['inventoryMode'] == 'ansible':
        print(json.dumps(ansibleInventoryDump()))

    ## options for users
    if oParser()['inventoryMode'] == 'all':
        print(json.dumps(inventoryDump('all')))

    if oParser()['inventoryMode'] == 'groups':
        print(json.dumps(inventoryDump('groups')))

    if oParser()['inventoryMode'] == 'hosts':
        print(json.dumps(inventoryDump('hosts')))

    if oParser()['addMode'] is not None:
        znodeDict = splitZnodeVarString(oParser()['addMode'])
        print(addHostWithHostvars(znodeDict))

    if oParser()['groupMode'] is not None:
        znodeStringSplited = splitZnodeString(oParser()['groupMode'])
        print(addHostToGroup(znodeStringSplited))
 
    if oParser()['updateMode'] is not None:
        znodeDict = splitZnodeVarString(oParser()['updateMode'])
        print(updateZnode(znodeDict))
        
    if oParser()['deleteMode'] is not None:
        znodeStringSplited = splitZnodeString(oParser()['deleteMode'])
        print(deleteZnodeRecur(znodeStringSplited))

    if oParser()['renameMode'] is not None:
        znodeRenameStringSplited = splitRenameZnodeString(oParser()['renameMode'])
        if type(znodeRenameStringSplited) is list:
            print(renameZnode(znodeRenameStringSplited))
        else:
            print(znodeRenameStringSplited)
            
    if oParser()['showMode'] is not None:
        znodeStringSplited = splitZnodeString(oParser()['showMode'])
        print(json.dumps(showHostVars(znodeStringSplited)))

    if oParser()['importToml'] is not None:
        print(importFromToml(oParser()['importToml']))

    if oParser()['exportToml'] is not None:
        print(exportToToml(oParser()['exportToml']))

    if oParser()['importIni'] is not None:
        print(importFromIni(oParser()['importIni']))

    if oParser()['exportIni'] is not None:
        print(exportToIni(oParser()['exportIni']))
                                  
        
if __name__ == "__main__":
    main()
