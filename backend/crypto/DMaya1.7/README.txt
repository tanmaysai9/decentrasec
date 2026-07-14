=========================
USE DOCUMENT
Last updated: 08-05-2020
=========================
Update Logs:
 + large file supported, max: chunks size: 500MB
 + indexing to organize output files

Encrypt application:
======================
Syntax:
-------
DMaya1.7-enc <inputFile> <outputDirectory>

Sample:
-------
DMaya1.7-enc test.iso .\new\

=======================
Decrypt application:
=======================
DMaya1.7-dec <inputDirectory> <outputFile>

Sample Input Json String at Command-line:
-----------------------------------------
DMaya1.7-dec new output.iso