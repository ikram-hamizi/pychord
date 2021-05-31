import logging
import sys
import serverxmlrpc
import clientxmlrpc
import random
from stabilizer import Stabilizer

from key import Key, Uid

log = logging.getLogger()
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(' %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

class BasicNode(object):
    def __init__(self, *args):
        """
        params are either ip and port OR a dict with keys ip and port 
        {"ip":<ip>, "port": <port>}
        """
        if len(args) == 2:
            ip = args[0]
            port = args[1]
        elif len(args) == 1:
            ip = args[0]["ip"]
            port = args[0]["port"]
        else:
            raise ValueError("len args of {} unsupported".format(len(args)))
        self.ip = ip
        self.port = port
        #TODO:optimization with sys.intern() str of 64 char
        self.uid = Uid(self.ip + ":" + repr(self.port))

    def getUid(self):
        return self.uid

    def asdict(self):
        """
        Creates and returns a dict with attr of the instance
        The dict can be used in rpc args
        """
        return {"ip": self.ip,
                "port": self.port,
                "uid": self.uid.value}

class NodeInterface(BasicNode):
    """
    Interface to call method on specified node
    When needed to use method from node N, N could be self.
    This class has the purpose  to abstract the choice of doing straightforward
    call on method if the node is self or to do RPC if it's a remote one

    If type of `arg` is LocalNode
    the NodeInterface object uses methods from it directly

    If type of `arg` is dict, we assume it is a remote node
    RPC will be done on arg["ip"] and arg["port"]
    (as a BasicNose is constructed from values of arg see BasicNode.__init__())

    @param arg: directly passed to BasicNode constructor
    """
    def __init__(self, arg):
        if isinstance(arg, LocalNode):
            super(NodeInterface, self).__init__(arg.ip, arg.port)
            self.methodProxy = arg
        elif isinstance(arg, dict):
            super(NodeInterface, self).__init__(arg)
            self.methodProxy = clientxmlrpc.ChordClientxmlrpcProxy(self.ip, self.port)
        else:
            raise TypeError("Supports LocalNode or dict")

class Finger(object):
    def __init__(self, key, originNode, respNode):
        """
        @param originNode
        @param respNode: dict or NodeInterface
        """
        if isinstance(originNode, LocalNode):
            self.originNode = originNode
        else:
            raise TypeError("originNode have to be LocalNode")

        #set key attr
        if isinstance(key, str):
            self.key = Key(key)
        elif isinstance(key, Key):
            self.key = key
        else:
            raise TypeError("key type not accepted. Support str and Key")

        self.setRespNode(respNode)

    def setRespNode(self, respNode):
        if isinstance(respNode, dict):
            self.respNode = self.originNode.getNodeInterface(respNode)
        elif isinstance(respNode, NodeInterface):
            self.respNode = respNode
        else:
            raise TypeError("Finger.setRespNode() accept dict and NodeInterface")

class LocalNode(BasicNode):
    def __init__(self, ip, port, _stabilizer=True):
        BasicNode.__init__(self, ip, port)
        self.predecessor = None
        self.fingers = []
        self.createfingertable()

        self.server = serverxmlrpc.ChordServerxmlrpc(self)
        self.server.start()

        self._stabilizer = _stabilizer
        if _stabilizer:
            self.stabilizer = Stabilizer(self)
            self.stabilizer.start()

    @property
    def successor(self):
        return self.fingers[0].respNode

    def asdict(self):
        return {"ip": self.ip,
                "port": self.port,
                "uid": self.uid.value,
                "succ": self.fingers[0].respNode.asdict()}

    def stop(self):
        if self._stabilizer:
            self.stabilizer.stop()
        self.stopXmlRPCServer()

    def stopXmlRPCServer(self):
        self.server.stop()

    def createfingertable(self):
        """
        Create fingers table
        Calculate all fingerkey and initializze all to self
        """
        selfinterface = NodeInterface(self)
        for i in range(0, self.uid.idlength):
            self.fingers.append(Finger(self.calcfinger(i), self, selfinterface))

    def setsuccessor(self, successor):
        """
        Create a NodeInterface object and set to self.fingers[0].respnode
        which is also self.successor

        @param successor: dict with ip and port as key
        """
        self.fingers[0].setRespNode(self.getNodeInterface(successor))
    
    def setpredecessor(self, predecessor):
        """
        Create a NodeInterface object and set to self.predecessor

        @param predecessor: dict with ip and port as key
        """
        self.predecessor = self.getNodeInterface(predecessor)

    def getsuccessor(self):
        return self.fingers[0].respNode.asdict()

    def getpredecessor(self):
        if self.predecessor:
            return self.predecessor.asdict()
        else:
            return None

    def getNodeInterface(self, nodedict):
        """
        Return a NodeInterface object
        Compare self and nodedict to provide localNode or not
        """
        if nodedict["ip"] == self.ip and nodedict["port"] == self.port:
            return NodeInterface(self)
        else:
            return NodeInterface(nodedict)

    def join(self, node):
        """
        Join method as described in the 4th paragraph
        """
        self.init_fingers(node)
        self.update_others()

    def join_5(self, nodeToJoin):
        """
        Join method as described in 5th paragraph
        """
        #self.predecessor = None
        self.setsuccessor(nodeToJoin.methodProxy.find_successor(self.uid))

    def _stabilize_and_fix_fingers(self):
        """
        Execute stabilize() and fix_fingers()
        """

        self.stabilize()
        self.fix_fingers()

    def stabilize(self):
        node_inter = self.successor.methodProxy.getpredecessor()
        if node_inter:
            if node_inter["uid"] == self.uid:
                """
                successor's predecessor is self so everything is fine
                Dont do anything
                """
                return
            if self.uid == self.successor.uid\
                    or Key(node_inter["uid"]).is_between_exclu(self.uid, self.successor.uid):
                self.setsuccessor(node_inter)
        if self.successor.uid != self.uid:
            self.successor.methodProxy.notify_new_predecessor(self.asdict())

    def notify_new_predecessor(self, new_predecessor):
        """
        Check wether `new_predecessor` is more accurate than current
        self.predecessor. If so, change accordingly

        This methods aims to be used by remote node which think they might
        be self.predecessor

        @param new_predecessor: dict node which might be our predecessor
        """
        if not self.predecessor\
                or Key(new_predecessor["uid"]).is_between_exclu(self.predecessor.uid, self.uid):
            self.setpredecessor(new_predecessor)

    def fix_fingers(self):
        i = random.randint(1, self.uid.idlength - 1)
        self.fingers[i].setRespNode(self.find_successor(self.fingers[i].key))

    def init_fingers(self, existingnode):
        #log.debug("%s - init_fingers with %s" %(self.uid, existingnode.uid))
        log.debug("PORT=%s - init_fingers with PORT=%s" %(self.port, existingnode.port))
        find_pred_res = existingnode.methodProxy.find_predecessor(self.uid.value)
        self.setsuccessor(find_pred_res["succ"])
        self.setpredecessor(find_pred_res)
        self.predecessor.methodProxy.setsuccessor(self.asdict()) # added compare to paper
        self.successor.methodProxy.setpredecessor(self.asdict())
        for i in range(0, self.uid.idlength - 1):
            if self.fingers[i + 1].key.isbetween(self.fingers[i].key, self.fingers[i].respNode.uid): #changed from paper's algo which use self.uid in place of fingers[I].key
                self.fingers[i + 1].setRespNode(self.fingers[i].respNode)
            else:
                nextfingersucc = existingnode.methodProxy.find_successor(
                        self.fingers[i+1].key)
                self.fingers[i+1].setRespNode(nextfingersucc)

    def update_others(self):
        print_top = 5
        for i in range(0, self.uid.idlength):
            #log.debug("%s - update_others for i=%i" %(self.uid, i))
            if i < print_top:
                log.debug("PORT=%s - update_others for i=%i (print Top-5 only)" %(self.port, i))

            predenode = self.find_predecessor(self.uid - pow(2, i))
            self.getNodeInterface(predenode).methodProxy.update_finger_table(self.asdict(), i)

    def update_finger_table(self, callingnode, i):
        callingnode = BasicNode(callingnode)
        #update_finger_table looped over the ring and came back to self
        if callingnode.uid == self.uid:
            return
        
        #log.debug("%s - update_finger_table with node '%s' for i=%i" %(self.uid, callingnode.uid, i))
        print_top = 5
        if i < print_top:
            log.debug("PORT=%s - update_finger_table with node '%s' for i=%i" %(self.port, callingnode.port, i))
           
        #TODO check if key and node uid of the same finger could be equal and then lead to a exception in isbetween
        if callingnode.uid.isbetween(self.fingers[i].key, self.fingers[i].respNode.uid):
            #log.debug("%s - update_finger_table:  callingnode uid is between self.uid and fingers(%i). node.uid" %(self.uid, i))
            if i < print_top:
                log.debug("PORT=%s - update_finger_table:  callingnode uid is between self.uid and fingers(%i). node.uid" %(self.port, i))            
            self.fingers[i].setRespNode(callingnode.asdict())
            #TODO optim : self knows fingers[i] uid so it can calculate if predecessor has chance or not to have to update his finger(i)
            if self.predecessor.uid != callingnode.uid: # dont rpc on callingnode it self
                self.predecessor.methodProxy.update_finger_table(callingnode.asdict(), i)

    def find_successor(self, key):
        """
        Lookup method for successor of key
        Use predecessor, successor and fingers information
        Should produce the same answer than lookupWithSucc
        """
        prednode = self.find_predecessor(key)
        return prednode["succ"]

    def find_predecessor(self, key):
        """
        Return the node which precede the provided key
        If key is equal to a node uid N, the return value is N.predecessor

        Return a dict which contains keys `ip`, `port`, `uid` and `succ`
        which is it self a dict defining a node

        """
        if isinstance(key, dict):
            key = key["value"]
            key = Key(key)
        elif isinstance(key, str):
            key = Key(key)
        if not isinstance(key, Key):
            raise TypeError("find_predecessor arg must be dict, str or Key")

        #log.debug("%s - find_predecessor for '%s'" %(self.uid, key.value))      
        
        log.debug("PORT=%s - find_predecessor for Key ='%s'" %(self.port, key.value))
        
        if self.uid == self.successor.uid:
            return self.asdict()
        if key.is_between_r_inclu(self.uid, self.successor.uid):
            return self.asdict()
        #TODO IDEA maybe: overwrite dispatch on xmlrpc server
        # then it is possible to dispatch on specific method for rpc
        # so in the next line case we are not force to transform cloPrecedFinger into a NodeInterface
        #TODO avoid casting directly in NodeInterface because we loose potential succ info from the original dict
        cloPrecedFinger= self.getNodeInterface(self.closest_preceding_finger(key.value))
        cloPrecedFingerSucc = BasicNode(cloPrecedFinger.methodProxy.getsuccessor())
        if cloPrecedFinger.uid == cloPrecedFingerSucc.uid:
            #TODO Here, self noticed that node has wrong fingers, should I correct it ?
            resdict = cloPrecedFinger.asdict()
            resdict["succ"] = cloPrecedFingerSucc.asdict()
            return resdict
        while not key.is_between_r_inclu(cloPrecedFinger.uid, cloPrecedFingerSucc.uid):
            cloPrecedFingerDict = cloPrecedFinger.methodProxy.closest_preceding_finger(key.value)
            if hasattr(cloPrecedFingerDict, "succ"):
                #TODO in test, is this if usefull ?
                breakpoint() #probably not...
                cloPrecedFingerSucc = self.getNodeInterface(cloPrecedFingerDict["succ"])
            else:
                cloPrecedFinger = self.getNodeInterface(cloPrecedFingerDict)
                if cloPrecedFinger.uid == self.uid:
                    cloPrecedFingerSucc = BasicNode(self.getsuccessor())
                else:
                    cloPrecedFingerSucc = BasicNode(cloPrecedFinger.methodProxy.getsuccessor())
        resdict = cloPrecedFinger.asdict()
        resdict["succ"] = cloPrecedFingerSucc.asdict()
        return resdict

    def closest_preceding_finger(self, keyvalue):
        """
        Return the closest preceding known node of provided keyvalue

        if keyvalue == self.uid -> self.predecessor
        Iterates reversly on fingers to find the closest known one.
        """
        if self.uid == keyvalue:
            return self.predecessor.asdict()
        for i in range(self.uid.idlength - 1, -1, -1):
            if self.fingers[i].respNode.uid == self.uid:
                if self.successor.uid == self.uid:
                    return self.asdict() #self is alone on the ring
                if Key(keyvalue).is_between_r_inclu(self.uid, self.successor.uid):
                    return self.asdict()
                continue
            if self.fingers[i].respNode.uid.is_between_exclu(self.uid, keyvalue):
                return self.fingers[i].respNode.asdict()
        return self.asdict()

    def updatefinger(self, firstnode):
        '''
        Update finger table
        Dummy update wich loookup all fingerkey
        When finished, propagate updatefinger to all node of the ring
        /!\ Very costly in rpc /!\
        finger is an array of dict {resp, key}
            `resp` is the Node responsible for `key`
        @param firstnode: node which launch the update
        '''
        for i in range(0, self.uid.idlength):
            resp = self.lookupWithSucc(self.fingers[i].key)
            self.fingers[i].setRespNode(resp)
        if firstnode.uid != self.fingers[0].respNode.uid:
            self.fingers[0].respNode.methodProxy.updatefinger(firstnode)

    def lookupWithSucc(self, key):
        """
        Lookup method which uses only successor information
        Provided a key, lookupWithSucc return a dict with basic info
        about the responsible node of the provided key

        @param key: key to look for the responsible
        """
        if isinstance(key, Key):
            keyLookedUp = key
        elif isinstance(key, str): #idlength
            keyLookedUp = Key(key)
        else:
            raise TypeError

        # Self is successor ?
        if self.uid == keyLookedUp:
            return {"ip": self.ip, "port": self.port}
        # Is self.successor the successor of key ?
        if keyLookedUp.isbetween(self.uid.value, self.successor.uid.value):
            return {"ip": self.successor.ip, "port": self.successor.port}

        return self.successor.methodProxy.lookupWithSucc(key)

    def calcfinger(self, k):
        '''
        Returns computed key for finger k
        @param k: from 0 to (m - 1)
        '''
        if k > self.uid.idlength - 1:
            raise ValueError("calcfinger: value above {} are not accepted".format(self.idlength))
        return self.uid + pow(2, k)

    def printFingers(self):
        for n, f in enumerate(self.fingers):
            print("TABLE: finger{0} : "
                "- key: {2} - resp: {1}"
                .format(n, f.respNode.uid, f.key))
            #if f["resp"].uid.value != self.lookupfinger(n, useOnlySucc=True).uid.value:
                #self.log.error("error between finger table and computed value")
                #continue
