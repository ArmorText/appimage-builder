#  Copyright  2019 Alexis Lopez Zubieta
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.

import os
import shutil
import subprocess
import logging

from AppImageBuilder.FileUtils import make_link_relative


class PkgTool:
    target_arch = None
    def __init__(self):
        self.logger = logging.getLogger("PkgTool")
        self.target_arch = self.get_deb_host_arch()

    def find_owner_packages(self, path):
        packages = []

        result = subprocess.run(["dpkg-query", "-S", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        errors = result.stderr.decode('utf-8')

        for line in errors.splitlines():
            if line.startswith("dpkg-query: no path found matching pattern"):
                self.logger.error(line)

        for line in output.splitlines():
            packages = self._parse_package_names_from_dpkg_query_output(line)

            for package in packages:
                if self.target_arch in packages:
                    # only use packages matching the target arch
                    packages.append(package)

        return set(packages)

    @staticmethod
    def _parse_package_names_from_dpkg_query_output(line):
        line = line.replace(',', '')
        sections = line.split(" ")
        # remove file path
        sections.pop()
        packages = []
        for package in sections:
            # remove last ',' or ':'
            package = package[:-1]
            packages.append(package)

        return packages

    def list_package_files(self, package):
        files = []

        result = subprocess.run(["dpkg-query", "-L", package], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')

        if result.returncode != 0:
            return files

        for line in output.splitlines():
            if os.path.isfile(line):
                files.append(line)

        return files

    def deploy_pkgs(self, pkgs, app_dir_path):
        extracted_files = {}
        for pkg in pkgs:
            self.logger.info("Deploying package: %s" % pkg)
            files = self.list_package_files(pkg)

            for file in files:
                target_file = app_dir_path + file
                self.logger.info("Deploying %s", file)

                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                shutil.copy2(file, target_file)

                extracted_files[file] = pkg
                if os.path.islink(target_file):
                    self._make_links_relative_to_app_dir(app_dir_path, target_file)

        return extracted_files

    @staticmethod
    def _make_links_relative_to_app_dir(app_dir, target_file):
        link_target = os.readlink(target_file)
        if link_target.startswith("/"):
            logging.info("Making link %s relative to %s", link_target, app_dir)
            make_link_relative(app_dir, target_file, link_target)

    def _extract_pkg_to(self, pkg_file, target_dir):
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        target_dir = os.path.abspath(target_dir)

        command = ["dpkg-deb", "-X", pkg_file, target_dir]
        self.logger.debug(command)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=target_dir)
        self.logger.info("Deployed files:\n%s" % result.stdout.decode('utf-8'))

        if result.returncode != 0:
            self.logger.error("Package extraction failed. Error: " + result.stderr.decode('utf-8'))
            return []

        return result.stdout.decode('utf-8').splitlines()

    def _extract_pkgs_to(self, temp_dir, appdir):
        extraction_map = {}
        for root, dirs, files in os.walk(temp_dir):
            for filename in files:
                if filename.endswith(".deb"):
                    self.logger.info("Extracting: %s" % filename)
                    extracted_files = self._extract_pkg_to(os.path.join(root, filename), appdir)

                    for extracted_file in extracted_files:
                        extraction_map[extracted_file] = os.path.basename(filename)

        return extraction_map

    @staticmethod
    def get_deb_host_arch():
        result = subprocess.run(["dpkg-architecture", "-q", 'DEB_HOST_ARCH'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return result.stdout.decode('utf-8').strip()
        else:
            return None