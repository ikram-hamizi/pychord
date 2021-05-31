import unittest
import chord
import tests.commons

class TestJoinTwoNodeRing(unittest.TestCase):
    def setUp(self):
        print("----------------\n"\
              "Creating 2 Nodes\n"\
              "----------------")
        self.nodes = tests.commons.createlocalnodes(2, stabilizer=False)

    def tearDown(self):
        tests.commons.stoplocalnodes(self.nodes)

    def test_join(self):
        
        print("\n--------------------------"\
              "\nJoining Node(1) to Node(2)"\
              "\n--------------------------"\
              "\n")
              
        self.nodes[1].join(chord.NodeInterface(self.nodes[0].asdict()))
        self.assertEqual(self.nodes[1].successor.uid, self.nodes[0].uid)
        self.assertEqual(self.nodes[0].successor.uid, self.nodes[1].uid)
        self.assertEqual(self.nodes[0].predecessor.uid, self.nodes[1].uid)
        self.assertEqual(self.nodes[1].predecessor.uid, self.nodes[0].uid)
        
        for k, node in enumerate(self.nodes):
            othernode = self.nodes[(k+1) % 2]
            for i in range(0, node.uid.idlength):
                if node.fingers[i].key.isbetween(node.uid, othernode.uid):
                    self.assertEqual(
                            node.fingers[i].respNode.uid,
                            othernode.uid
                    )
                else:
                    self.assertEqual(
                            node.fingers[i].respNode.uid,
                            node.uid
                    )

class TestJoinThreeNodeRing(unittest.TestCase):
    def setUp(self):
        self.nodes = tests.commons.createlocalnodes(3, stabilizer=False)

    def tearDown(self):
        tests.commons.stoplocalnodes(self.nodes)

    def test_join_three_node(self):
        
        self.nodes[1].join(chord.NodeInterface(self.nodes[0].asdict()))
        self.nodes[2].join(chord.NodeInterface(self.nodes[0].asdict()))

        for k, node in enumerate(self.nodes):
            node1 = self.nodes[(k+1) % len(self.nodes)]
            node2 = self.nodes[(k+2) % len(self.nodes)]
            if node.uid.isbetween(node1.uid, node2.uid):
                nodesuccessor = node2
                nodepredecessor = node1
            else:
                nodesuccessor = node1
                nodepredecessor = node2
            # Assert predecessor and successor
            self.assertEqual(
                    node.predecessor.uid,
                    nodepredecessor.uid
            )
            self.assertEqual(
                    node.successor.uid,
                    nodesuccessor.uid
            )
            #Loop to assert all fingers of node
            for i in range(0, node.uid.idlength):
                if node.fingers[i].key.isbetween(node.uid, nodesuccessor.uid):
                    self.assertEqual(
                            node.fingers[i].respNode.uid,
                            nodesuccessor.uid
                    )
                elif node.fingers[i].key.isbetween(nodesuccessor.uid, nodepredecessor.uid):
                    self.assertEqual(
                            node.fingers[i].respNode.uid,
                            nodepredecessor.uid
                    )
                else:
                    self.assertEqual(
                            node.fingers[i].respNode.uid,
                            node.uid
                    )
