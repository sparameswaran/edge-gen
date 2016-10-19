#!/usr/bin/env python

# tile-generator
#
# Copyright (c) 2015-Present Pivotal Software, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import errno
import glob
import requests
import shutil
import stat
import subprocess
import tarfile
import template
import urllib
import zipfile
import yaml
import re
import datetime

from bosh import *
from util import *
from subprocess import Popen, PIPE, STDOUT


LIB_PATH = os.path.dirname(os.path.realpath(__file__))
REPO_PATH = os.path.realpath(os.path.join(LIB_PATH, '..'))
DOCKER_BOSHRELEASE_VERSION = '23'

# Directories to save the generated code
RELEASE_BUILD       = 'release-build'
TILE_METADATA_BUILD = 'tile-metadata-build'

def dumpclean(obj):
    if type(obj) == dict:
        for k, v in obj.items():
            if hasattr(v, '__iter__'):
                print k
                dumpclean(v)
            else:
                print '%s : %s' % (k, v)
    elif type(obj) == list:
        for v in obj:
            if hasattr(v, '__iter__'):
                dumpclean(v)
            else:
                print v
    else:
        print obj

def build(config, verbose=False):
    context = setup_config(config)
    
    build_jobs(context)
    build_tile_metadata(context)
    

def build_tile_metadata(context, verbose=False):    
    with cd(TILE_METADATA_BUILD, clobber=True):
        gen_tile_metadata('tile-templates', context)
        gen_scripts('scripts', context)

    print 'Generated tile metadata: ' + os.path.realpath(os.path.join(TILE_METADATA_BUILD))    

def build_jobs(context, verbose=False):
    with cd(RELEASE_BUILD, clobber=True):
        gen_release_dir('config', context)
        gen_jobs('jobs', context)
        gen_packages('packages', context)
        mkdir_p('src')
        mkdir_p('blobs')
        #add_apigee_rpm(context)
        #add_openjdk(context)
        #bosh('upload', 'blobs')
        #output = bosh('create', 'release', '--force', '--final', '--with-tarball', '--version', context['version'])
        # context['release'] = bosh_extract(output, [
        #     { 'label': 'name', 'pattern': 'Release name' },
        #     { 'label': 'version', 'pattern': 'Release version' },
        #     { 'label': 'manifest', 'pattern': 'Release manifest' },
        #     { 'label': 'tarball', 'pattern': 'Release tarball' },
        # ])
        # #gen_tile('tile-output', context)
    print 'Generated release: ' + os.path.realpath(os.path.join(RELEASE_BUILD))
    print 'Blobs need to be added before creating release\n'

def setup_config(config, verbose=False):
    # Clean up config (as above)
    context = config.copy()
    #add_defaults(context)
    context['verbose'] = verbose
    validate_config(context)
    return context



def validate_config(context):
    context['root_dir'] = os.getcwd()
    name = context['product']['name'].lower().replace(' ', '-')   
    if (name.endswith('service-adapter') != True):
        name += '-service-adapter'

    context['product']['name'] = name
    context['product']['short_name'] = context['product']['short_name'].lower().replace(' ', '-')
    context['product']['title'] = context['product']['short_name'].title()
    context['release_version'] = context.get('release_version', context['version'])
    context['product']['enabled_groups'] = context['product'].get('enabled_groups', ['edge'] )
    context['product']['additions'] = []
    for group in context['product']['enabled_groups']:
        if group != 'edge':
            context['product']['additions'].append(group)

    context['services'] = context.get('services')
    context['enabled_groups'] = context['product']['enabled_groups']

    apigee_mirror_service = {}
    apigee_mirror_service['name'] = 'yum-repo'
    apigee_mirror_service['type'] = 'apigee-mirror'
    apigee_mirror_service['group'] = 'edge'
    context['services'].append(apigee_mirror_service)
    
    validate_components_config(context)
    context['setup_complete'] = True

def validate_components_config(context):
    index = 0

    component_list = context['components']
    # Reset components to be empty and add components that are enabled
    context['components'] = []

    for component in component_list:
        component['group'] = component.get('group', 'edge') # default group is edge
        
        #print ' Component  ' + component['name'] + ' depends on ' + dependsOn
        if component['group'] not in context['enabled_groups']:
            continue

        component['name'] = component['name'].replace('_', '-').replace(' ', '-')
        component['name_lower'] = component['name'].lower()
        component['title'] = component['name_lower'].replace('-', ' ').title()
        component['title'] = component['title'].replace('Baas', 'BaaS').replace('Qpid', 'QPid')
        component['service_type'] = component['name_lower'].replace('apigee-','').replace('edge-', '').replace('baas-', '')
        component['service_name'] = component['service_type']

        component['uses_single_az'] = str(component.get('uses_single_az', 'false')).lower()

        instances = component.get('instances')
        instances['configurable'] = instances.get('configurable', 'true')
        instances['default_instances'] = instances.get('default_instances', 1)
        instances['min_instances'] = instances.get('min_instances', instances['default_instances'])
        instances['uses_odd_or_zero_instances'] = instances.get('uses_odd_or_zero_instances', 'false')
        
        persistence = component.get('persistence')
        persistence['default_persistent_disk'] = persistence.get('default_persistent_disk', 10240)
        persistence['persistent_disk_configurable'] = persistence.get('persistent_disk_configurable', 'true')
        
        component['sub_components'] = component.get('sub_components', [])
        component['controlled_install'] = component.get('controlled_install', 'false')
        #dumpclean(component)
        context['components'].append(component)    
        
    #dumpclean(context['components'])
    

def gen_release_dir(dir, context, alternate_template=None):
    release_dir = os.path.realpath(os.path.join(dir ))
    
    template_dir = dir
    release_context = {
        'context': context,
        'product': context['product'],
        #'managed_service_release_jobs': context['managed_service_release_jobs'],
        'files': []
    }
    template.render(
        os.path.join(release_dir, 'blobs.yml'),
        os.path.join(template_dir, 'blobs.yml' ),
        release_context
    )
    template.render(
        os.path.join(release_dir, 'final.yml'),
        os.path.join(template_dir, 'final.yml' ),
        release_context
    )    

def copyanything(src, dst):
    try:
        shutil.copytree(src, dst)
    except OSError as exc: # python >2.5
        if exc.errno == errno.ENOTDIR:
            shutil.copy(src, dst)
        else: raise

def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        try:
            if os.path.isdir(s):
                shutil.copytree(s, d, symlinks, ignore)
            else:
                shutil.copy2(s, d)
        except IOError as exc:
            mkdir_p(dst)
            if os.path.isdir(s):
                shutil.copytree(s, d, symlinks, ignore)
            else:
                shutil.copy2(s, d)        

def gen_jobs(dir, context, alternate_template=None):
    jobs_dir = os.path.realpath(os.path.join(dir ))
    
    template_dir = dir
    jobs_context = {
        'context': context,
        'product': context['product'],
        #'managed_service_release_jobs': context['managed_service_release_jobs'],
        'files': []
    }

    #shutil.copytree(context['root_dir'] + '/templates/jobs/apigee-mirror',  jobs_dir + '/')   
    #shutil.copytree(context['root_dir'] + '/templates/jobs/apigee-validation-test',  jobs_dir + '/')
    copyanything(context['root_dir'] + '/templates/jobs/apigee-mirror',  jobs_dir)
    copytree(context['root_dir'] + '/templates/jobs/apigee-validation-test',  jobs_dir + '/apigee-validation-test') 
    
    for component in context['components']:

        jobs_context['component'] = component
        template.render(
            os.path.join(jobs_dir, component['name'] + '/monit'),
            os.path.join(template_dir, 'component/monit' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/spec'),
            os.path.join(template_dir, 'component/spec' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/apigee-license.txt.erb'),
            os.path.join(template_dir, 'component//templates/apigee-license.txt.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/application-override.properties.erb'),
            os.path.join(template_dir, 'component//templates/application-override.properties.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/component.sh.erb'),
            os.path.join(template_dir, 'component//templates/component.sh.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/default.properties.erb'),
            os.path.join(template_dir, 'component//templates/default.properties.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/drain.erb'),
            os.path.join(template_dir, 'component//templates/drain.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/init.sh.erb'),
            os.path.join(template_dir, 'component//templates/init.sh.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/pre-start.erb'),
            os.path.join(template_dir, 'component//templates/pre-start.erb' ),
            jobs_context
        )
        template.render(
            os.path.join(jobs_dir, component['name'] + '/templates/silent.conf.erb'),
            os.path.join(template_dir, 'component//templates/silent.conf.erb' ),
            jobs_context
        )   

        for sub_component in component['sub_components']:
            jobs_context['sub_component'] = sub_component
            #jobs_context['sub_component_type'] = sub_component.replace('apigee-','').replace('edge-', '').replace('baas-', '')

            #print 'Rendering sub_component: ' + sub_component
            template.render(
                os.path.join(jobs_dir, component['name'] + '/templates/' + sub_component + '.properties.erb'),
                os.path.join(template_dir, 'component//templates/sub-component-override.properties.erb' ),
                jobs_context
            )


def gen_packages(dir, context, alternate_template=None):
    packages_dir = os.path.realpath(os.path.join(dir ))
    
    mkdir_p(packages_dir)
    template_dir = dir
    if alternate_template is not None:
        template_dir = os.path.join(template_dir, alternate_template)
    packages_context = {
        'context': context,
        'product': context['product'],
        #'managed_service_release_jobs': context['managed_service_release_jobs'],
        'files': []
    }    

    template.render(
        os.path.join(packages_dir, 'apigee-mirror/packaging'),
        os.path.join(template_dir, 'apigee-mirror/packaging' ),
        packages_context
    )
    template.render(
        os.path.join(packages_dir, 'apigee-mirror/spec'),
        os.path.join(template_dir, 'apigee-mirror/spec' ),
        packages_context
    )
    template.render(
        os.path.join(packages_dir, 'component/spec'),
        os.path.join(template_dir, 'component/spec' ),
        packages_context
    )
    template.render(
        os.path.join(packages_dir, 'component/packaging'),
        os.path.join(template_dir, 'component/packaging' ),
        packages_context
    )

def add_blobs(context, alternate_template=None):
    for resource in context['resources']:
        file_name = resource['file'].replace('resources/', '')
        print 'File name: ' + file_name
        add_blob_package(context,
            {
                'name': resource['name'],
                'files': [{
                    'name': file_name,
                    'path': context['root_dir'] + '/' + resource['file']
                }]
            }
        )



def gen_tile_metadata(dir, context, alternate_template=None):
    tile_dir = os.path.realpath(os.path.join(dir ))
    context['product']['tile']['version'] = context['version']
    
    mkdir_p(tile_dir)
    template_dir = 'tile'
    if alternate_template is not None:
        template_dir = os.path.join(template_dir, alternate_template)

    #dumpclean(context['product']['tile'])

    tile_context = {
        'context': context,
        'product': context['product'],
        'history': context['history'],
        'version': context['version'],
        'release_version': context['release_version'],
        'tile'   : context['product']['tile'],
        'components': context['components'],
        'services': context['services'],
        'files': []
    }

    template.render(
        os.path.join(tile_dir, 'content-migrations.yml'),
        os.path.join(template_dir, 'content-migrations.yml' ),
        tile_context
    )
    template.render(
        os.path.join(tile_dir, 'migration.js'),
        os.path.join(template_dir, 'migration.js' ),
        tile_context
    )
    template.render(
        os.path.join(tile_dir, context['product']['short_name'] + '-tile.yml'),
        os.path.join(template_dir, 'apigee-edge-tile.yml'),
        tile_context
    )


def gen_scripts(dir, context, alternate_template=None):
    scripts_dir = os.path.realpath(os.path.join(dir ))
    context['product']['tile']['version'] = context['version']
    
    mkdir_p(scripts_dir)
    template_dir = dir
    if alternate_template is not None:
        template_dir = os.path.join(template_dir, alternate_template)
    
    tile_context = {
        'context': context,
        'root_dir': context['root_dir'],
        'product': context['product'],
        'history': context['history'],
        'version': context['version'],
        'tile'   : context['product']['tile'],
        'files': []
    }
    

    template.render(
        os.path.join(scripts_dir, 'createRelease.sh'),
        os.path.join(template_dir, 'createRelease.sh' ),
        tile_context
    )
    template.render(
        os.path.join(scripts_dir, 'createTile.sh'),
        os.path.join(template_dir, 'createTile.sh' ),
        tile_context
    )

    tileScript = os.stat(scripts_dir + '/createTile.sh')
    os.chmod(scripts_dir + '/createTile.sh', tileScript.st_mode | stat.S_IEXEC)
    releaseScript = os.stat(scripts_dir + '/createRelease.sh')
    os.chmod(scripts_dir + '/createRelease.sh', releaseScript.st_mode | stat.S_IEXEC)


def gen_tile(dir, context, alternate_template=None):
    release_dir = os.getcwd()
    tile_output_dir = os.path.realpath(os.path.join(dir ))
    #print './scripts/createTile.sh', ' '.join([release_dir, tile_output_dir])
    command = [ './scripts/createTile.sh'] + [ release_dir, tile_output_dir ]
    try:
        #return subprocess.check_output(command, stderr=subprocess.STDOUT, cwd=release_dir)
        cmd = './scripts/createTile.sh ' + release_dir + ' ' + tile_output_dir 
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
        output = p.stdout.read()
        print output
    except subprocess.CalledProcessError as e:
        print e.output
        sys.exit(e.returncode)


def add_blob_package(context, package, alternate_template=None):
    add_package('blobs', context, package, alternate_template)

# FIXME dead code, remove.
def add_package(dir, context, package, alternate_template=None):
    name = package['name'].lower().replace('-','_')
    package['name'] = name
    bosh('generate', 'package', name)
    target_dir = os.path.realpath(os.path.join(dir, name))
    package_dir = os.path.realpath(os.path.join('packages', name))
    mkdir_p(target_dir)
    template_dir = 'packages'
    if alternate_template is not None:
        template_dir = os.path.join(template_dir, alternate_template)
    package_context = {
        'context': context,
        'package': package,
        'files': []
    }
    with cd('..'):
        files = package.get('files', [])
        path = package.get('path', None)
        if path is not None:
            files += [ { 'path': path } ]
            package['path'] = os.path.basename(path)
        manifest = package.get('manifest', None)
        manifest_path = None
        if type(manifest) is dict:
            manifest_path = manifest.get('path', None)
        if manifest_path is not None:
            files += [ { 'path': manifest_path } ]
            package['manifest']['path'] = os.path.basename(manifest_path)
        for file in files:
            filename = file.get('name', os.path.basename(file['path']))
            file['name'] = filename
            urllib.urlretrieve(file['path'], os.path.join(target_dir, filename))
            package_context['files'] += [ filename ]
        for docker_image in package.get('docker_images', []):
            filename = docker_image.lower().replace('/','-').replace(':','-') + '.tgz'
            download_docker_image(docker_image, os.path.join(target_dir, filename), cache=context.get('docker_cache', None))
            package_context['files'] += [ filename ]
    if package.get('is_app', False):
        manifest = package.get('manifest', { 'name': name })
        if manifest.get('random-route', False):
            print >> sys.stderr, 'Illegal manifest option in package', name + ': random-route is not supported'
            sys.exit(1)
        manifest_file = os.path.join(target_dir, 'manifest.yml')
        with open(manifest_file, 'wb') as f:
            f.write('---\n')
            f.write(yaml.safe_dump(manifest, default_flow_style=False))
        package_context['files'] += [ 'manifest.yml' ]
        update_memory(context, manifest)
    template.render(
        os.path.join(package_dir, 'spec'),
        os.path.join(template_dir, 'spec'),
        package_context
    )
    template.render(
        os.path.join(package_dir, 'packaging'),
        os.path.join(template_dir, 'packaging'),
        package_context
    )


# FIXME dead code, remove.
def bosh(*argv):
    argv = list(argv)
    print 'bosh', ' '.join(argv)
    command = [ 'bosh', '--no-color', '--non-interactive' ] + argv
    try:
        return subprocess.check_output(command, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        if argv[0] == 'init' and argv[1] == 'release' and 'Release already initialized' in e.output:
            return e.output
        if argv[0] == 'generate' and 'already exists' in e.output:
            return e.output
        print e.output
        sys.exit(e.returncode)

# FIXME dead code, remove.
def bash(*argv):
    argv = list(argv)
    try:
        return subprocess.check_output(argv, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print ' '.join(argv), 'failed'
        print e.output
        sys.exit(e.returncode)

def is_semver(version):
    valid = re.compile('[0-9]+\\.[0-9]+\\.[0-9]+([\\-+][0-9a-zA-Z]+(\\.[0-9a-zA-Z]+)*)*$')
    return valid.match(version) is not None

def is_unannotated_semver(version):
    valid = re.compile('[0-9]+\\.[0-9]+\\.[0-9]+$')
    return valid.match(version) is not None

def update_version(history, version):
    if version is None:
        version = 'patch'
    prior_version = history.get('version', None)
    if prior_version is not None:
        history['history'] = history.get('history', [])
        history['history'] += [ prior_version ]
    if not is_semver(version):
        semver = history.get('version', '0.0.0')
        if not is_unannotated_semver(semver):
            print >>sys.stderr, 'The prior version was', semver
            print >>sys.stderr, 'To auto-increment, the prior version must be in semver format (x.y.z), and must not include a label.'
            sys.exit(1)
        semver = semver.split('.')
        if version == 'patch':
            semver[2] = str(int(semver[2]) + 1)
        elif version == 'minor':
            semver[1] = str(int(semver[1]) + 1)
            semver[2] = '0'
        elif version == 'major':
            semver[0] = str(int(semver[0]) + 1)
            semver[1] = '0'
            semver[2] = '0'
        else:
            print >>sys.stderr, 'Argument must specify "patch", "minor", "major", or a valid semver version (x.y.z)'
            sys.exit(1)
        version = '.'.join(semver)
    history['version'] = version
    return version
