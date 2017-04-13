#!/usr/bin/python
# <variable> = required
# Usage ./lava-report.py <option> [json]
import os
import urlparse
import xmlrpclib
import json
import argparse
import time
import subprocess
import re
import urllib2
import requests
import shutil

from lib import configuration
from lib import utils

#log2html = 'https://git.linaro.org/people/kevin.hilman/build-scripts.git/blob_plain/HEAD:/log2html.py'

device_map = {'arndale': ['exynos5250-arndale', 'exynos'],
              'snow': ['exynos5250-snow', 'exynos'],
              'arndale-octa': ['exynos5420-arndale-octa','exynos'],
              'panda-es': ['omap4-panda-es', 'omap2'],
              'panda': ['omap4-panda', 'omap2'],
              'omap5-uevm' : ['omap5-uevm', 'omap2' ],
              'hi3716cv200': ['hisi-x5hd2-dkb', 'hisi'],
              'd01': ['hip04-d01', 'hisi'],
              'd02': ['hip05-d02', 'hisi'],
              'd03': ['hip06-d03', 'hisi'],
              'd03_zsj_test': ['hip06-d03', 'hisi'],
              'd05': ['d05_01', 'hisi'],
              #'dummy_ssh': ['hip05-d02', 'hisi'],
              'hi6220-hikey': ['hi6220-hikey', 'hisi'],
              'qemu-arm-cortex-a15': ['vexpress-v2p-ca15-tc1', 'vexpress'],
              'qemu-arm-cortex-a15-a7': ['vexpress-v2p-ca15_a7', 'vexpress'],
              'qemu-arm-cortex-a9': ['vexpress-v2p-ca9', 'vexpress'],
              'qemu-arm': ['versatilepb', 'versatile'],
              'qemu-aarch64': ['qemu-aarch64', 'qemu'],
              'juno': ['juno', 'arm'],
              'juno-kvm-host': ['juno-kvm-host', 'arm'],
              'juno-kvm-guest': ['juno-kvm-guest', 'arm'],
              'juno-kvm-uefi-host': ['juno-kvm-uefi-host', 'arm'],
              'juno-kvm-uefi-guest': ['juno-kvm-uefi-guest', 'arm'],
              'x86': ['x86', None],
              'dummy-ssh': ['dummy-ssh', None],
              'dummy_ssh_d02': ['dummy_ssh_d02', None],
              'dummy_ssh_d01': ['dummy_ssh_d01', None],
              'dummy_ssh_d03': ['dummy_ssh_d03', None],
              'dummy_ssh_d03_zsj_test': ['dummy_ssh_d03_zsj_test', None],
              'dummy_ssh_d05': ['dummy_ssh_d05', None],
              'kvm': ['x86-kvm', None]}


def download_log2html(url):
    print 'Fetching latest log2html script'
    try:
        response = urllib2.urlopen(url, timeout=30)
    except IOError, e:
        print 'error fetching %s: %s' % (url, e)
        exit(1)
    script = response.read()
    utils.write_file(script, 'log2html.py', os.getcwd())


def parse_json(json):
    jobs = utils.load_json(json)
    url = utils.validate_input(jobs['username'], jobs['token'], jobs['server'])
    connection = utils.connect(url)
    duration = jobs['duration']
    # Remove unused data
    jobs.pop('duration')
    jobs.pop('username')
    jobs.pop('token')
    jobs.pop('server')
    return connection, jobs, duration

def push(method, url, data, headers):
    retry = True
    while retry:
        if method == 'POST':
            response = requests.post(url, data=data, headers=headers)
        elif method == 'PUT':
            response = requests.put(url, data=data, headers=headers)
        else:
            print "ERROR: unsupported method"
            exit(1)
        if response.status_code != 500:
            retry = False
            print "OK"
        else:
            time.sleep(10)
            print response.content

# add by wuyanjun
def get_board_type(directory, filename):
    strinfo = re.compile('.txt')
    json_name = strinfo.sub('.json', filename)
    test_info = utils.load_json(os.path.join(directory, json_name))
    if 'board' in test_info.keys():
        # for dummy-ssh board
        board_type = ''
        try:
            if re.search('ssh', test_info['board_instance']):
                board_type = test_info['board_instance'].split('_')[0]
            else:
                if ',' in test_info['board']:
                    board_verify = test_info['board'].split(',')[0]
                    for key in device_map.keys():
                        if device_map[key][0] == board_verify:
                            board_type = key
                            break
                        else:
                            board_type = ''
                else:
                    # for dummy_ssh_{board_type}
                    board_type = test_info['board'].split('_')[-1]
        except KeyError:
            if ',' in test_info['board']:
                try:
                    board_verify = test_info['board'].split(',')[0]
                except:
                    board_verify = test_info['board']
                    for key in device_map.keys():
                        if device_map[key][0] == board_verify:
                            board_type = key
                            break
                        else:
                            board_type = ''
            else:
                # for jobs which has not incomplete
                board_type = test_info['board'].split('_')[-1]
        return board_type
    return ''

# add by wuyanjun
def get_board_instance(directory, filename):
    strinfo = re.compile('.txt')
    json_name = strinfo.sub('.json',filename)
    #with open(os.path.join(directory, json_name), "r") as lines:
    test_info = utils.load_json(os.path.join(directory, json_name))
    if 'board_instance' in test_info.keys():
            board_instance = test_info['board_instance']
            return board_instance
    return ''

# add by wuyanjun
# we use the plans all by 'UPPER CASE'
def get_plans(directory, filename):
    m = re.findall('[A-Z]+_?[A-Z]*', filename)
    if m:
        root_dir = directory
        while '.git' not in os.listdir(root_dir):
            root_dir = os.path.join(root_dir, os.path.pardir)
        root_dir = os.path.abspath(root_dir)
        for item in m:
            for root, dirs, files in os.walk(os.path.join(root_dir, "boot-app-scripts", "templates")):
                for dir_item in dirs:
                    if dir_item == item:
                       return item
    return ''

# add by wuyanjun
# parser the test result
def parser_and_get_result(contents, filename, directory, report_directory, connection):
    summary_post = '_summary.txt'
    if filename.endswith('.txt'):
        board_type = get_board_type(directory, filename)
        plan = get_plans(report_directory, filename)
        if board_type and plan:
            summary = board_type + '_' + plan + summary_post
        elif board_type:
            summary = board_type + summary_post
        elif plan:
            summary = plan + summary_post
        else:
            summary = 'summary.txt'
        if 'dummy_ssh' in filename or 'dummy-ssh' in filename:
            with open(os.path.join(report_directory, summary), 'a') as sf:
                job_id = filename.split("_")[-1].split(".")[0]
                with open(os.path.join(directory, filename)) as fp:
                    lines = fp.readlines()
                write_flag = 0
                # for job which has been run successfully
                with open(os.path.join(directory, filename)) as fp:
                    contents = fp.read()
                if re.search("=+", contents) and re.search('Test.*?case.*?Result', contents):
                    for i in range(0, len(lines)):
                        line = lines[i]
                        if write_flag == 1:
                            sf.write(line)
                            continue
                        if re.search("=+", line) and re.search("=+", lines[i+2]) and re.search('Test.*?case.*?Result', lines[i+3]):
                            write_flag = 1
                            sf.write("job_id is: %s\n" % job_id)
                            sf.write(line)
                    sf.write('\n')
                # for jobs which is Incomplete
                else:
                    job_details = connection.scheduler.job_details(job_id)
                    job_name = re.findall('testdef.*\/(.*?)\.yaml', job_details['original_definition'])
                    sf.write("job_id is: %s\n" % job_id)
                    sf.write("="*13 + "\n")
                    sf.write(' '.join(job_name) + "\n")
                    sf.write("="*13 + "\n")
                    sf.write(' '.join(job_name) + "_test_cases\t\tFAIL\n\n")

# add by wuyanjun
# get the ip address of boards for the application jobs
def get_ip_board_mapping(contents, filename, directory, report_directory):
    ip_address = 'device_ip_type.txt'
    ip_address_path = os.path.join(report_directory, ip_address)
    with open(ip_address_path, 'a') as sf:
        match = re.findall('addr:(\d+\.\d+\.\d+\.\d+)\s+Bcast', contents)
        if not match:
            match_array = re.findall('inet\s+(\d+\.\d+\.\d+\.\d+).*brd', contents)
            if len(match_array):
                match = match_array
        if match:
            board_type = get_board_type(directory, filename)
            board_instance = get_board_instance(directory, filename)
            sf.write(board_type + '\t' + board_instance +
                '\t' + match[-1] + '\n' )

def boot_report(config):
    connection, jobs, duration =  parse_json(config.get("boot"))
    # TODO: Fix this when multi-lab sync is working
    #download_log2html(log2html)
    results_directory = os.getcwd() + '/results'
    results = {}
    utils.mkdir(results_directory)
    test_plan = None

    if config.get("lab"):
        report_directory = os.path.join(results_directory, config.get("lab"))
    else:
        report_directory = results_directory
    if os.path.exists(report_directory):
        shutil.rmtree(report_directory)
    utils.mkdir(report_directory)

    for job_id in jobs:
        print 'Job ID: %s' % job_id
        # Init
        boot_meta = {}
        api_url = None
        arch = None
        board_instance = None
        boot_retries = 0
        kernel_defconfig_full = None
        kernel_defconfig = None
        kernel_defconfig_base = None
        kernel_version = None
        device_tree = None
        kernel_endian = None
        kernel_tree = None
        kernel_addr = None
        initrd_addr = None
        dtb_addr = None
        dtb_append = None
        fastboot = None
        fastboot_cmd = None
        job_file = ''
        board_offline = False
        kernel_boot_time = None
        boot_failure_reason = None
        efi_rtc = False
        # Retrieve job details
        device_type = ''
        job_details = connection.scheduler.job_details(job_id)
        if job_details['requested_device_type_id']:
            device_type = job_details['requested_device_type_id']
        if job_details['description']:
            job_name = job_details['description']
            try:
                job_short_name = re.search(".*?([A-Z]+.*)", job_name).group(1)
            except Exception:
                job_short_name = 'boot-test'
        try:
            device_name = job_details['_actual_device_cache']['hostname']
        except Exception:
            continue
        result = jobs[job_id]['result']
        bundle = jobs[job_id]['bundle']
        if not device_type:
            device_type = job_details['_actual_device_cache']['device_type_id']
        if bundle is None and device_type == 'dynamic-vm':
            host_job_id = job_id.replace('.1', '.0')
            bundle = jobs[host_job_id]['bundle']
            if bundle is None:
                print '%s bundle is empty, skipping...' % device_type
                continue
        # Retrieve the log file
        try:
            binary_job_file = connection.scheduler.job_output(job_id)
        except xmlrpclib.Fault:
            print 'Job output not found for %s' % device_type
            continue
        # Parse LAVA messages out of log
        raw_job_file = str(binary_job_file)
        for line in raw_job_file.splitlines():
            if 'Infrastructure Error:' in line:
                print 'Infrastructure Error detected!'
                index = line.find('Infrastructure Error:')
                boot_failure_reason = line[index:]
                board_offline = True
            if 'Bootloader Error:' in line:
                print 'Bootloader Error detected!'
                index = line.find('Bootloader Error:')
                boot_failure_reason = line[index:]
                board_offline = True
            if 'Kernel Error:' in line:
                print 'Kernel Error detected!'
                index = line.find('Kernel Error:')
                boot_failure_reason = line[index:]
            if 'Userspace Error:' in line:
                print 'Userspace Error detected!'
                index = line.find('Userspace Error:')
                boot_failure_reason = line[index:]
            if '<LAVA_DISPATCHER>' not in line:
                if len(line) != 0:
                    job_file += line + '\n'
            if 'rtc-efi rtc-efi: setting system clock to' in line:
                if device_type == 'dynamic-vm':
                    efi_rtc = True

        # Retrieve bundle
        if bundle is not None:
            json_bundle = connection.dashboard.get(bundle)
            bundle_data = json.loads(json_bundle['content'])
            # Get the boot data from LAVA
            for test_results in bundle_data['test_runs']:
                # Check for the LAVA self boot test
                if test_results['test_id'] == 'lava':
                    for test in test_results['test_results']:
                        # TODO for compat :(
                        if test['test_case_id'] == 'kernel_boot_time':
                            kernel_boot_time = test['measurement']
                        if test['test_case_id'] == 'test_kernel_boot_time':
                            kernel_boot_time = test['measurement']
                    bundle_attributes = bundle_data['test_runs'][-1]['attributes']
            if utils.in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                print bundle_attributes['kernel.defconfig']
            if utils.in_bundle_attributes(bundle_attributes, 'target'):
                board_instance = bundle_attributes['target']
            if utils.in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                kernel_defconfig = bundle_attributes['kernel.defconfig']
                defconfig_list = kernel_defconfig.split('-')
                #arch = defconfig_list[0]
                arch = defconfig_list[-1]
                # Remove arch
                defconfig_list.pop(0)
                kernel_defconfig_full = '-'.join(defconfig_list)
                kernel_defconfig_base = ''.join(kernel_defconfig_full.split('+')[:1])
                if kernel_defconfig_full == kernel_defconfig_base:
                    kernel_defconfig_full = None
            if utils.in_bundle_attributes(bundle_attributes, 'kernel.version'):
                kernel_version = bundle_attributes['kernel.version']
            if utils.in_bundle_attributes(bundle_attributes, 'device.tree'):
                device_tree = bundle_attributes['device.tree']
            if utils.in_bundle_attributes(bundle_attributes, 'kernel.endian'):
                kernel_endian = bundle_attributes['kernel.endian']
            if utils.in_bundle_attributes(bundle_attributes, 'platform.fastboot'):
                fastboot = bundle_attributes['platform.fastboot']
            if kernel_boot_time is None:
                if utils.in_bundle_attributes(bundle_attributes, 'kernel-boot-time'):
                    kernel_boot_time = bundle_attributes['kernel-boot-time']
            if utils.in_bundle_attributes(bundle_attributes, 'kernel.tree'):
                kernel_tree = bundle_attributes['kernel.tree']
            if utils.in_bundle_attributes(bundle_attributes, 'kernel-addr'):
                kernel_addr = bundle_attributes['kernel-addr']
            if utils.in_bundle_attributes(bundle_attributes, 'initrd-addr'):
                initrd_addr = bundle_attributes['initrd-addr']
            if utils.in_bundle_attributes(bundle_attributes, 'dtb-addr'):
                dtb_addr = bundle_attributes['dtb-addr']
            if utils.in_bundle_attributes(bundle_attributes, 'dtb-append'):
                dtb_append = bundle_attributes['dtb-append']
            if utils.in_bundle_attributes(bundle_attributes, 'boot_retries'):
                boot_retries = int(bundle_attributes['boot_retries'])
            if utils.in_bundle_attributes(bundle_attributes, 'test.plan'):
                test_tmp = bundle_attributes['test.plan']
                if test_tmp:
                    test_plan = test_tmp
        else:
            if not kernel_defconfig or not kernel_version or not kernel_tree:
                job_defnition = {}
                if 'original_definition' in job_details.keys():
                    job_definition = job_details['original_definition']
                    try:
                        job_dictionary = eval(job_definition)
                    except Exception:
                        pass
                    if job_dictionary:
                        if 'actions' in job_dictionary.keys():
                            actions = job_dictionary['actions']
                            for i in range(0, len(actions)):
                                try:
                                    kernel_defconfig = actions[i]['metadata']['kernel.defconfig']
                                    kernel_version = actions[i]['metadata']['kernel.version']
                                    kernel_tree = actions[i]['metadata']['kernel.tree']
                                    kernel_endian = actions[i]['metadata']['kernel.endian']
                                    platform_fastboot = actions[i]['metadata']['platform.fastboot']
                                    device_tree = actions[i]['metadata']['kernel.tree']
                                    break
                                except KeyError:
                                    continue
                if 'target' in job_details.keys():
                    print job_details.keys()
        # Check if we found efi-rtc
        if test_plan == 'boot-kvm-uefi' and not efi_rtc:
            if device_type == 'dynamic-vm':
                boot_failure_reason = 'Unable to read EFI rtc'
                result = 'FAIL'

        # Record the boot log and result
        # TODO: Will need to map device_types to dashboard device types
        if kernel_defconfig and device_type and result:
            if ( 'arm' == arch or 'arm64' == arch ) and device_tree is None:
                platform_name = device_map[device_type][0] + ',legacy'
            else:
                if test_plan == 'boot-nfs' or test_plan == 'boot-nfs-mp':
                    platform_name = device_map[device_type][0] + '_rootfs:nfs'
                else:
                    platform_name = device_map[device_type][0]

            # Create txt format boot metadata
            print 'Creating boot log for %s' % (platform_name + job_name + '_' + job_id)
            log = 'boot-%s.txt' % (platform_name + job_name + '_' + job_id)
            html = 'boot-%s.html' % (platform_name + job_name + '_' + job_id)
            if config.get("lab"):
                directory = os.path.join(results_directory, kernel_defconfig + '/' + config.get("lab"))
            else:
                directory = os.path.join(results_directory, kernel_defconfig)
            utils.ensure_dir(directory)

            utils.write_file(job_file, log, directory)

            if kernel_boot_time is None:
                kernel_boot_time = '0.0'
            if results.has_key(kernel_defconfig):
                results[kernel_defconfig].append({'device_type': platform_name,
                    'job_id': job_id, 'job_name': job_short_name,
                    'kernel_boot_time': kernel_boot_time, 'result': result,
                    'device_name': device_name})
            else:
                results[kernel_defconfig] = [{'device_type': platform_name,
                    'job_id': job_id, 'job_name': job_short_name,
                    'kernel_boot_time': kernel_boot_time, 'result': result,
                    'device_name': device_name}]

            # Create JSON format boot metadata
            print 'Creating JSON format boot metadata'
            if config.get("lab"):
                boot_meta['lab_name'] = config.get("lab")
            else:
                boot_meta['lab_name'] = None
            if board_instance:
                boot_meta['board_instance'] = board_instance
            boot_meta['retries'] = boot_retries
            boot_meta['boot_log'] = log
            boot_meta['boot_log_html'] = html
            # TODO: Fix this
            boot_meta['version'] = '1.0'
            boot_meta['arch'] = arch
            boot_meta['defconfig'] = kernel_defconfig_base
            if kernel_defconfig_full is not None:
                boot_meta['defconfig_full'] = kernel_defconfig_full
            if device_map[device_type][1]:
                boot_meta['mach'] = device_map[device_type][1]
            boot_meta['kernel'] = kernel_version

            boot_meta['job'] = kernel_tree
            boot_meta['board'] = platform_name
            if board_offline and result == 'FAIL':
                boot_meta['boot_result'] = 'OFFLINE'
                #results[kernel_defconfig]['result'] = 'OFFLINE'
            else:
                boot_meta['boot_result'] = result
            if result == 'FAIL' or result == 'OFFLINE':
                if boot_failure_reason:
                    boot_meta['boot_result_description'] = boot_failure_reason
                else:
                    boot_meta['boot_result_description'] = 'Unknown Error: platform failed to boot'
            boot_meta['boot_time'] = kernel_boot_time
            # TODO: Fix this
            boot_meta['boot_warnings'] = None
            if device_tree:
                if arch == 'arm64':
                    boot_meta['dtb'] = 'dtbs/' + device_map[device_type][1] + '/' + device_tree
                else:
                    boot_meta['dtb'] = 'dtbs/' + device_tree
            else:
                boot_meta['dtb'] = device_tree
            boot_meta['dtb_addr'] = dtb_addr
            boot_meta['dtb_append'] = dtb_append
            boot_meta['endian'] = kernel_endian
            boot_meta['fastboot'] = fastboot
            # TODO: Fix this
            boot_meta['initrd'] = None
            boot_meta['initrd_addr'] = initrd_addr
            if arch == 'arm':
                boot_meta['kernel_image'] = 'zImage'
            elif arch == 'arm64':
                boot_meta['kernel_image'] = 'Image'
            else:
                boot_meta['kernel_image'] = 'bzImage'
            boot_meta['loadaddr'] = kernel_addr
            json_file = 'boot-%s.json' % (platform_name + job_name + '_' + job_id)
            utils.write_json(json_file, directory, boot_meta)
            # add by wuyanjun
            # add the ip device mapping
            get_ip_board_mapping(job_file, log, directory, report_directory)
            parser_and_get_result(job_file, log, directory, report_directory, connection)

    if results and kernel_tree and kernel_version:
        print 'Creating summary for %s' % (kernel_version)
        boot = '%s-boot-report.txt' % (kernel_version)
        if test_plan and ('boot' in test_plan or 'BOOT' in test_plan):
            boot = boot.replace('boot', test_plan)
        passed = 0
        failed = 0
        for defconfig, results_list in results.items():
            for result in results_list:
                if result['result'] == 'PASS':
                    passed += 1
                else:
                    failed += 1
        total = passed + failed
        with open(os.path.join(report_directory, boot), 'a') as f:
            f.write('Subject: %s boot: %s boots: %s passed, %s failed (%s)\n' % (kernel_tree,
                                                                                str(total),
                                                                                str(passed),
                                                                                str(failed),
                                                                                kernel_version))
            f.write('\n')
            f.write('Total Duration: %.2f minutes\n' % (duration / 60))
            f.write('Tree/Branch: %s\n' % kernel_tree)
            f.write('Git Describe: %s\n' % kernel_version)
            first = True
            for defconfig, results_list in results.items():
                for result in results_list:
                    if result['result'] == 'OFFLINE':
                        if first:
                            f.write('\n')
                            f.write('Boards Offline:\n')
                            first = False
                        f.write('\n')
                        f.write(defconfig)
                        f.write('\n')
                        break
                for result in results_list:
                    if result['result'] == 'OFFLINE':
                        f.write('    %s   %s   %s   %ss   %s: %s\n' % (result['job_id'],
                                                                    result['device_type'],
                                                                    result['device_name'],
                                                                    result['kernel_boot_time'],
                                                                    result['job_name'],
                                                                    result['result']))
                        f.write('\n')
            first = True
            for defconfig, results_list in results.items():
                for result in results_list:
                    if result['result'] == 'FAIL':
                        if first:
                            f.write('\n')
                            f.write('Failed Boot Tests:\n')
                            first = False
                        f.write('\n')
                        f.write(defconfig)
                        f.write('\n')
                        break
                for result in results_list:
                    if result['result'] == 'FAIL':
                        f.write('    %s   %s   %s   %ss   %s: %s\n' % (result['job_id'],
                                                                    result['device_type'],
                                                                    result['device_name'],
                                                                    result['kernel_boot_time'],
                                                                    result['job_name'],
                                                                    result['result']))
            f.write('\n')
            f.write('Full Boot Report:\n')
            for defconfig, results_list in results.items():
                f.write('\n')
                f.write(defconfig)
                f.write('\n')
                for result in results_list:
                    f.write('    %s   %s   %s   %ss   %s: %s\n' %
                                                                    (result['job_id'],
                                                                        result['device_type'],
                                                                        result['device_name'],
                                                                        result['kernel_boot_time'],
                                                                        result['job_name'],
                                                                        result['result']))

def main(args):
    config = configuration.get_config(args)

    if config.get("boot"):
        boot_report(config)
    exit(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="configuration for the LAVA server")
    parser.add_argument("--section", default="default", help="section in the LAVA config file")
    parser.add_argument("--boot", help="creates a kernel-ci boot report from a given json file")
    parser.add_argument("--lab", help="lab id")
    parser.add_argument("--api", help="api url")
    parser.add_argument("--token", help="authentication token")
    parser.add_argument("--email", help="email address to send report to")
    args = vars(parser.parse_args())
    main(args)
