from socket import *
import sys
import _thread as thread
from datetime import datetime

maxConn = int(sys.argv[2])
maxSize = int(sys.argv[3])

if(maxConn==0):
	maxConn = 2047
if(maxSize==0):
	maxSize = 9223372036854775807

no = 0
noConn = 0
cacheSize = 0.0

proxyPort = int(sys.argv[1]) #proxy port set with sys.argv[1]
proxySocket = socket(AF_INET,SOCK_STREAM) #setup proxy socket
proxySocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1) #for break address using when this source finished 
proxySocket.bind(('',proxyPort)) #bind proxy socket

# list for caching
# element: tuple of URL & response & status & content type
cache = []

def analyseRequest(request): #analyse Request
	requestHeader = {} #declare request header dic
	requestBodyCri = request.find(b"\r\n\r\n") #find body with "\r\n\r\n"
	requestBody = request[requestBodyCri+4:] #delcare request body with cri
	requestHeaderLines = request[:requestBodyCri].split(b"\r\n") #list of request header lines
	method, url, ver = requestHeaderLines.pop(0).split(b' ') #method, url, ver of first line

	host = url.split(b"//")[-1].split(b"/")[0] #find out host with url
	for requestHeaderLine in requestHeaderLines: #with each header line of list
		cri = requestHeaderLine.find(b": ") 
		if cri:
			requestHeader[requestHeaderLine[:cri]] = requestHeaderLine[cri+2:] #fill request header dictionary

	mobile = False
	userAgent = False
	if b'User-Agent' in requestHeader.keys(): #if User-Agent in request header
		userAgent = requestHeader[b'User-Agent'] #setup user agent
		if any(x in requestHeader[b'User-Agent'].lower() for x in [b'mobile',b'iphone',b'android',b'tablet',b'nexus']):
			mobile = True #if mobile was detected in User-Agent, setup variale mobile
	return method, url, host, ver, userAgent, mobile, requestHeader, requestBody

def analyseResponse(response): #analyse Response
	responseHeader = {} #declare response header dic
	responseBodyCri = response.find(b"\r\n\r\n") #find body cri with "\r\n\r\n"
	responseBody = response[responseBodyCri+4:] #delcare response body with cri
	responseHeaderLines = response[:responseBodyCri].split(b"\r\n") #list of response header lines
	status = responseHeaderLines.pop(0) #get status with first element of the list
	ver = status[:8] #ver is first 8 char of status
	status = status[9:] #else chars
	for responseHeaderLine in responseHeaderLines: #with each header line of list
		cri = responseHeaderLine.find(b": ")
		if cri:
			responseHeader[responseHeaderLine[:cri]] = responseHeaderLine[cri+2:] #fill request header dictionary
	contentType = None
	contentLength = None
	connection = None
	if b'Content-Type' in responseHeader.keys():
		contentType = responseHeader[b'Content-Type'] #get content-type
	if b'Content-Length' in responseHeader.keys():
		contentLength = responseHeader[b'Content-Length'] #get content-length
	if b'Connection' in responseHeader.keys():
		connection = responseHeader[b'Connection'] #get connection
	return status, ver, responseHeader, responseBody, contentType, contentLength, connection

def assembleChunk(assembleChunk):
	contentLength = 0 #declare content Length
	lastChunk = False #we can judge this assembleChunk is last or not with this lastChunk
	if assembleChunk.find(b'Content-Length') >= 0: #if here is content-length
		lengthStart = assembleChunk.find(b'Content-Length')+16
		lengthEnd = assembleChunk[assembleChunk.find(b'Content-Length')+16:].find(b'\r\n')
		contentLength = int(assembleChunk[lengthStart:lengthStart+lengthEnd]) # get content-length in assembleChunk
	if assembleChunk.find(b'\r\n0\r\n\r\n') >= 0: #if here is \r\n0\r\n\r\n
		lastChunk = True #judge this assembleChunk is last
	bodyLength = 0 #declare bodyLength
	if assembleChunk.find(b'\r\n\r\n'): #if here is \r\n\r\n
		bodyLength = len(assembleChunk[assembleChunk.find(b'\r\n\r\n')+4:]) #get body length
	if assembleChunk[:4] == b"HTTP":
		if assembleChunk[9:12] == b'304':
			lastChunk = True
	return contentLength, lastChunk, bodyLength

def getTime():
	rawData = str(datetime.now())
	space = rawData.find(' ')
	return rawData[space+1:len(rawData)-3]

def getMilSec(s, f):
	start = float(s[len(s)-6:])
	finish = float(f[len(s)-6:])
	tmp = int((finish-start)*1000)
	if tmp < 0:
		tmp += 1000
	return tmp

def infoFirstLine(no, noConn, maxConn, cacheSize, maxSize, lenCache):
	if(maxConn==2047 and maxSize==9223372036854775807):
		return ('%d [Conn: %d/MAX] [Cache: %.2f/MAX] [Items: %d]'%(no, noConn, cacheSize, lenCache))
	if(maxConn!=2047 and maxSize==9223372036854775807):
		return ('%d [Conn: %d/%d] [Cache: %.2f/MAX] [Items: %d]'%(no, noConn, maxConn, cacheSize, lenCache))
	if(maxConn==2047 and maxSize!=9223372036854775807):
		return ('%d [Conn: %d/MAX] [Cache: %.2f/%dMB] [Items: %d]'%(no, noConn, cacheSize, maxSize, lenCache))
	if(maxConn!=2047 and maxSize!=9223372036854775807):
		return ('%d [Conn: %d/%d] [Cache: %.2f/%dMB] [Items: %d]'%(no, noConn, maxConn, cacheSize, maxSize, lenCache))


def proxy():
	global no
	global noConn
	global cacheSize
	global cache

	while 1:
		loggingLineList = []
		clientSocket, addr = proxySocket.accept() #accept client socket
		noConn += 1
		clientSocket.settimeout(0.1) #setup timeout with 1 sec
		persistentHost = None #setup persistent host as None
	
		try:
			clientSocketRunning = True 
			while clientSocketRunning: #when client Socket running

				assembledRequest = b'' #declare assembled request 
				assemblingRequest = True
				while assemblingRequest: #assembling request
					request = clientSocket.recv(1024) #receive request
					if not request: #if not request, do not assemble request
						assemblingRequest = False
					assembledRequest += request #assemble more request
					if assembledRequest.find(b'\r\n\r\n') >= 0: #if assemble request has \r\n\r\n
						assemblingRequest = False #finish assembling

				if not assembledRequest: #if not request, break
					break

				method, url, host, ver, userAgent, mobile, requestHeader, requestBody = analyseRequest(assembledRequest) #analyse request
				
				if not persistentHost: #if not persistent connection
					no += 1
					loggingLineList.append(infoFirstLine(no, noConn, maxConn, cacheSize, maxSize, len(cache)))
					loggingLineList.append('[CLI connected to %s:%i]'%(addr))

				# check requested file is in cache
				found = False
				for c in cache:
					if url == c[0]:
						found = True
						cachedURL, cachedResponse, cachedStatus, cachedContentType = c
						break

				# CACHE HIT
				if found:
					host = host.decode() #decode host
					startTime = getTime()
					loggingLineList.append(" ".join(('[CLI ==> PRX --- SRV]', '@', startTime)))
					"".join(" ", )
					loggingLineList.append(" ".join((">",method.decode(), url.decode())))
					loggingLineList.append(" ".join((">",userAgent.decode())))
					loggingLineList.append("[SRV connected to %s:%i]" % (host, 80))
					loggingLineList.append('@@@@@@@@@@@@@@@@@@ CACHE HIT @@@@@@@@@@@@@@@@@@@@')
					clientSocket.send(cachedResponse)
					finishTime = getTime()
					loggingLineList.append(" ".join(('[CLI <== PRX --- SRV]', '@', finishTime)))
					loggingLineList.append(" ".join((">",cachedStatus.decode()))) #log status
					if cachedContentType:
						loggingLineList.append(" ".join((">",contentType.decode()))) #log type and size
					tmp = getMilSec(startTime, finishTime)
					loggingLineList.append('# %dms'%(tmp))
					clientSocket.close()
					loggingLineList.append('[CLI disconnected]')
					loggingLineList.append('[SRV disconnected]')
					loggingLineList.append("-----------------------------------------------")

					break

				host = host.decode() #decode host
				startTime = getTime()
				loggingLineList.append(" ".join(('[CLI ==> PRX --- SRV]', '@', startTime)))
				loggingLineList.append(" ".join((">",method.decode(), url.decode())))
				loggingLineList.append(" ".join((">",userAgent.decode())))

				if host.find(".")<0 and host != "localhost": #when host is error, break
					clientSocketRunning = False
					loggingLineList.append("[CLI disconnected]")
					clientSocket.close()
					loggingLineList.append("-----------------------------------------------")
					break

				if persistentHost != host: #if not persistent connection
					serverSocket = socket(AF_INET, SOCK_STREAM) #make new server socket
					serverSocket.connect((host,80)) 
					persistentHost = host
					loggingLineList.append("[SRV connected to %s:%i]" % (host, 80))

				serverSocket.send(assembledRequest) #send request to server socket
				loggingLineList.append('################## CACHE MISS ###################')
				loggingLineList.append(" ".join(('[CLI --- PRX ==> SRV]', '@', getTime())))
				loggingLineList.append(" ".join((">",method.decode(), url.decode())))
				loggingLineList.append(" ".join((">",userAgent.decode())))


				serverSocket.settimeout(1) #set time out of server socket

				#declare variables
				assembledChunk = b''
				accumulatedLength = 9223372036854775807
				bodyLength =0
				lastChunk =0
				AssemblingResponse = True
				serverError = False

				while AssemblingResponse: #assembling response
					try:
						chunk = serverSocket.recv(1024) #receive chunk
						if not chunk:
							break
						assembledChunk += chunk #assemble chunk
						contentLength, lastChunk, bodyLength = assembleChunk(assembledChunk) #assemble chunk and analyse
						if contentLength:
							accumulatedLength = contentLength
						if accumulatedLength <= bodyLength or lastChunk: #if this is last, end this loop
							AssemblingResponse = False
					except Exception as e: #if timeout error, this is server error
						AssemblingResponse = False
						serverError = True

				if serverError: #when server error
					clientSocketRunning = False #close client
					clientSocket.close()
					loggingLineList.append("[CLI disconnected]")
					serverSocket.close()
					loggingLineList.append("[SRV disconnected]")
					loggingLineList.append("-----------------------------------------------")
					break

				loggingLineList.append(" ".join(('[CLI --- PRX <== SRV]', '@', getTime())))
				status, ver, responseHeader, responseBody, contentType, contentLength, connection = analyseResponse(assembledChunk) #analyse response
				loggingLineList.append(" ".join((">",status.decode())))
				if contentType:
					loggingLineList.append(" ".join((">",contentType.decode())))

				# cache overflow
				while cacheSize+len(assembledChunk)/(1024*1024) >= maxSize:
					cacheSize -= len(cache[0][1])/(1024*1024)
					del cache[0]	# delete LRUed data

					loggingLineList.append('################# CACHE REMOVED #################')
					loggingLineList.append(" ".join(('> %s %.2fMB', (cache[0][0].decode(), len(cache[0][1])/(1024*1024)))))
					loggingLineList.append('> This file has been removed due to LRU !')
				
				# push response into cache
				cache.append((url, assembledChunk, status, contentType))
				cacheSize += len(assembledChunk)/(1024*1024)

				loggingLineList.append('################## CACHE ADDED ##################')
				loggingLineList.append('> %s %.2fMB'%(url.decode(), cacheSize))
				loggingLineList.append('> This file has been added to the cache')
				loggingLineList.append('#################################################')

				clientSocket.send(assembledChunk) #send response to client socket
				finishTime = getTime()
				loggingLineList.append(" ".join(('[CLI <== PRX --- SRV]', '@', finishTime)))
				loggingLineList.append(" ".join((">",status.decode()))) #log status
				if contentType:
					loggingLineList.append(" ".join((">",contentType.decode()))) #log type and size

				tmp = getMilSec(startTime, finishTime)
				loggingLineList.append('# %dms'%(tmp))

				if connection == b'close' or (ver == b'HTTP/1.0' and connection.decode().lower() != 'keep-alive'): #if close connection or (HTTP/1.0 and not keep-alive), then disconnect
					loggingLineList.append('[CLI disconnected]')
					clientSocket.close()
					loggingLineList.append('[SRV disconnected]')
					serverSocket.close()
					loggingLineList.append("-----------------------------------------------")
					clientSocketRunning = False

					break

		except Exception as e: # if client timeout error, deal it
			clientSocket.close() #close client socket
			if persistentHost: #if persistent connection, log these msg
				loggingLineList.append("[CLI disconnected]")
				clientSocket.close()
				loggingLineList.append("[SRV disconnected]")
				serverSocket.close()
				loggingLineList.append("-----------------------------------------------")
		if(len(loggingLineList)): #print log
			print(*loggingLineList, sep='\n')
		noConn -= 1


print("Starting proxy server on port %s" % proxyPort)
print("-----------------------------------------------")
proxySocket.listen(100)
NO = 0

# start maxConn instances of threads
for i in range(0, maxConn):
	try:
		thread.start_new_thread(proxy, ())
	except Exception as e:
		pass

# wait for threads
while 1:
	pass