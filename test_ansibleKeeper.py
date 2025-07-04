from ansibleKeeper import * 

def test_import_export_ini():
        '''
        Test for importFromIni() and exportToIni() functions.
        '''
        # Create a dummy INI file for testing
        with open("inven") as f:
            ini_file_path = "inven"

            # Test import
            importFromIni(ini_file_path)
            print(tst)
            ansibleDumpDict = {tst.groupName: {'hosts': sorted(tst.testDict[tst.groupName].keys()), 'vars': {}}, '_meta': {'hostvars': tst.testDict[tst.groupName]}}
            assert ansibleInventoryDump() == ansibleDumpDict

            # Test export
            export_ini_file_path = "test_export_inventory.ini"
            exportToIni(export_ini_file_path)

            # Clean up created files
            os.remove(ini_file_path)
            os.remove(export_ini_file_path)

            # Clean up Zookeeper nodes
            deleteZnodeRecur(splitZnodeString(tst.groupName))
            for hostname in tst.testDict[tst.groupName].keys():
                tmpHostStr = "hosts:{}".format(hostname)
                deleteZnodeRecur(splitZnodeString(tmpHostStr))



if __name__ == "__main__": 
    test_import_export_ini()
