from onsager import crystal, supercell, cluster
import numpy as np
import collections
import itertools
import Transitions
import Cluster_Expansion
import unittest
import time

class testKRA(unittest.TestCase):

    def setUp(self):
        self.NSpec = 3
        self.MaxOrder = 3
        self.crys = crystal.Crystal.BCC(0.2836, chemistry="A")
        self.jnetBCC = self.crys.jumpnetwork(0, 0.26)
        self.superlatt = 8 * np.eye(3, dtype=int)
        self.superBCC = supercell.ClusterSupercell(self.crys, self.superlatt)
        # get the number of sites in the supercell - should be 8x8x8
        numSites = len(self.superBCC.mobilepos)
        self.vacsite = cluster.ClusterSite((0, 0), np.zeros(3, dtype=int))
        self.vacsiteInd = self.superBCC.index(np.zeros(3, dtype=int), (0, 0))[0]
        self.mobOccs = np.zeros((self.NSpec, numSites), dtype=int)
        for site in range(1, numSites):
            spec = np.random.randint(0, self.NSpec-1)
            self.mobOccs[spec][site] = 1
        self.mobOccs[-1, self.vacsiteInd] = 1
        self.mobCountList = [np.sum(self.mobOccs[i]) for i in range(self.NSpec)]
        self.clusexp = cluster.makeclusters(self.crys, 0.29, self.MaxOrder)
        self.KRAexpander = Transitions.KRAExpand(self.superBCC, 0, self.jnetBCC, self.clusexp, self.mobCountList,
                                                 self.vacsite)
        self.VclusExp = Cluster_Expansion.VectorClusterExpansion(self.superBCC, self.clusexp, self.jnetBCC,
                                                                 self.mobCountList, self.vacsite, self.MaxOrder)

    def test_groupTrans(self):
        """
        To check if the group operations that form the clusters keep the transition sites unchanged.
        """
        for key, clusterLists in self.KRAexpander.SymTransClusters.items():

            ciA, RA = self.superBCC.ciR(key[0])
            ciB, RB = self.superBCC.ciR(key[1])
            siteA = cluster.ClusterSite(ci=ciA, R=RA)
            siteB = cluster.ClusterSite(ci=ciB, R=RB)
            self.assertEqual(siteA, self.vacsite)

            # Get the point group of this transition
            Glist = []
            for g in self.crys.G:
                siteANew = siteA.g(self.crys, g)
                siteBNew = siteB.g(self.crys, g)
                if siteA == siteANew and siteB == siteBNew:
                    Glist.append(g)

            clusterListCount = collections.defaultdict(int)  # each cluster should only appear in one list
            for clist in clusterLists:
                cl0 = clist[0]
                for clust in clist:
                    clusterListCount[clust] += 1
                    count = 0
                    for g in Glist:
                        clNew = cl0.g(self.crys, g)
                        if clNew == clust:
                            count += 1
                            # Check that every group operation which maps the starting cluster to some cluster
                            # in the list keeps the transition unchanged.
                            self.assertEqual(siteA, siteA.g(self.crys, g))
                            self.assertEqual(siteB, siteB.g(self.crys, g))
                    self.assertNotEqual(count, 0)
            for clust, count in clusterListCount.items():
                self.assertEqual(count, 1)

    def test_species_grouping(self):
        """
        The objective for this is to check that each clusterlist is repeated as many times as there should be
        species in its sites.
        """
        # First, count that every transition has every specJ at the end site
        clusterSpeciesJumps = self.KRAexpander.clusterSpeciesJumps

        counter = collections.defaultdict(int)
        for key, items in clusterSpeciesJumps.items():
            counter[(key[0], key[1])] += 1

        for key, item in counter.items():
            self.assertEqual(item, self.NSpec-1)

        # Now check that all possible atomic arrangements have been accounted for
        for key, SpeciesclusterLists in clusterSpeciesJumps.items():
            # check that the initial site is the vacancy site
            self.assertEqual(key[0], self.VclusExp.sup.index(self.vacsite.R, self.vacsite.ci)[0])
            clusterCounts = collections.defaultdict(int)
            for species, clusterList in SpeciesclusterLists:
                cl0 = clusterList[0]
                self.assertEqual(cl0.Norder, len(species))
                self.assertEqual(cl0.Norder+2, len(cl0.sites))
                clusterCounts[cl0] += 1

            for cl0, count in clusterCounts.items():
                numTrue = (self.NSpec-1)**cl0.Norder
                self.assertEqual(numTrue, count, msg="{}, {}, {}".format(numTrue, count, cl0.Norder))

    def test_KRA(self):
        """
        Checking whether the KRA expansions are done correctly
        """
        # Go through each transition
        for transition, clusterLists in self.KRAexpander.clusterSpeciesJumps.items():
            # get the number of clusterLists, and generate that many coefficients
            KRACoeffs = np.array([np.random.rand() for i in range(len(clusterLists))])
            valOn = np.zeros(len(KRACoeffs))
            # Now go through the clusterLists and note which clusters are on
            for Idx, (tup, clList) in enumerate(clusterLists):
                for cl in clList:
                    # check if this cluster is On
                    prod = 1
                    countVacSite = 0
                    countFinSite = 0
                    for siteInd, site in enumerate(cl.sites):
                        siteIdx = self.superBCC.index(site.R, site.ci)[0]
                        if siteInd == 0:
                            # vacancy site is always occupied by vacancy
                            countVacSite += 1
                            self.assertEqual(siteIdx, self.vacsiteInd)
                            self.assertEqual(self.mobOccs[-1, siteInd], 1)
                        elif siteInd == 1:
                            # SpecJ
                            countFinSite += 1
                            specJ = transition[2]
                            # check if this site is occupied
                            self.assertEqual(self.superBCC.index(site.R, site.ci)[0], transition[1])
                            if self.mobOccs[specJ][transition[1]] == 0:
                                continue  # this is not the transition we are looking for for this state
                        elif self.mobOccs[tup[siteInd - 2], siteIdx] == 0:
                            prod = 0

                    self.assertEqual(countFinSite, 1)
                    self.assertEqual(countVacSite, 1)

                    if prod == 1:
                        valOn[Idx] += KRACoeffs[Idx]

            KRAen = np.sum(valOn)
            KRAcalc = self.KRAexpander.GetKRA(transition, self.mobOccs, KRACoeffs)
            self.assertTrue(np.allclose(KRAen, KRAcalc), msg="{}, {}".format(KRAen, KRAcalc))
            # print("Envalues : {}, {}".format(KRAcalc, KRAen))


class test_Vector_Cluster_Expansion(testKRA):

    def test_genvecs(self):
        """
        Here, we test if we have generated the vector cluster basis (site-based only) properly
        """
        for clListInd, clList, vecList in zip(itertools.count(), self.VclusExp.vecClus,
                                              self.VclusExp.vecVec):
            self.assertEqual(len(clList), len(vecList))
            cl0, vec0 = clList[0], vecList[0]
            for clust, vec in zip(clList, vecList):
                # First check that symmetry operations are consistent
                count = 0
                for g in self.crys.G:
                    if cl0.g(self.crys, g) == clust:
                        count += 1
                        self.assertTrue(np.allclose(np.dot(g.cartrot, vec0), vec) or
                                        np.allclose(np.dot(g.cartrot, vec0) + vec, np.zeros(3)),
                                        msg="\n{}, {} \n{}, {}\n{}\n{}".format(vec0, vec, cl0, clust,
                                                                               self.crys.lattice, g.cartrot))
                self.assertGreater(count, 0)

    def testcluster2vecClus(self):

        for clListInd, clList in enumerate(self.VclusExp.SpecClusters):
            for clust in clList:
                vecList = self.VclusExp.clust2vecClus[clust]
                for tup in vecList:
                    self.assertEqual(clust, self.VclusExp.vecClus[tup[0]][tup[1]])

    def test_indexing(self):
        for vclusListInd, clListInd in enumerate(self.VclusExp.Vclus2Clus):
            cl0 = self.VclusExp.vecClus[vclusListInd][0]
            self.assertEqual(cl0, self.VclusExp.SpecClusters[clListInd][0])

    def test_activeClusters(self):
        """
         We do three tests here:
         (1) Every cluster is present as many times as it contains either vacancy (c,i) or final site's (c,i)
         (2) The transition vectors are the correct ones.
         (3) The clusters collected under the final sites, do not also contain vacSite when translated
        """
        clusterTransOff = self.VclusExp.clustersOff
        clusterTransOn = self.VclusExp.clustersOn

        # First, we test clusters that need to be turned off
        for stSpc, clustTupList in clusterTransOff.items():
            clusterCounts = collections.defaultdict(int)
            clust2Tup = collections.defaultdict(list)
            for clusterTup in clustTupList:
                transSites = clusterTup[2]
                siteList, specList = [tup[0] for tup in transSites], [tup[1] for tup in transSites]
                clust = Cluster_Expansion.ClusterSpecies(specList, siteList)
                # Check that we get back the correct representative cluster
                vecListInd, clustInd = clusterTup[0], clusterTup[1]
                self.assertEqual(self.VclusExp.vecClus[vecListInd][clustInd], clust,
                                 msg="{} \n {}".format(self.VclusExp.vecClus[vecListInd][clustInd], clust))
                clusterCounts[clust] += 1
                clust2Tup[clust].append(clusterTup)

            # Next, we check that a cluster is repeated as many times as it contains the species in the key
            # in a translated image of the site in the key, multiplied by the dimensionality of its vector basis.
            for clust, count in clusterCounts.items():
                c = 0
                for site, spec in clust.SiteSpecs:
                    if site.ci == stSpc[0].ci and spec == stSpc[1]:
                        Rtrans = stSpc[0].R - site.R
                        # What is the point of the check below - to prevent double counting
                        # re-verify this part again - how does this work?
                        if (self.VclusExp.vacSite, self.VclusExp.vacSpec) in [(site + Rtrans, spec)
                                                                              for site, spec in clust.SiteSpecs]:
                            if stSpc[0] != self.vacsite:
                                continue
                        c += 1
                # Now multiply the dimensionality of the vector basis

                dimBasis = 0
                for clustList in self.VclusExp.vecClus:
                    for cl in clustList:
                        if cl == clust:
                            dimBasis += 1

                self.assertEqual(c*dimBasis, count, msg="\nsite, species : {}\ncluster:{}\ncount:{}\n{}\ndimBasis:"
                                                        "{}\nc:{}".format(
                    stSpc, clust, count, clust2Tup[clust], dimBasis, c))

        # Next, we test the clusters that need to be turned on
        for stSpc, clustTupList in clusterTransOn.items():
            # clusterCounts = collections.defaultdict(int)
            # clust2Tup = collections.defaultdict(list)
            # for clusterTup in clustTupList:
            #     clusterCounts[clusterTup[2]] += 1
            #     clust2Tup[clusterTup[2]].append(clusterTup)
            clusterCounts = collections.defaultdict(int)
            clust2Tup = collections.defaultdict(list)
            for clusterTup in clustTupList:
                transSites = clusterTup[2]
                siteList, specList = [tup[0] for tup in transSites], [tup[1] for tup in transSites]
                clust = Cluster_Expansion.ClusterSpecies(specList, siteList)
                # creating a cluster object out of the sites will bring the centroid unit cell back to the origin.
                # Check that we get back the correct representative cluster
                vecListInd, clustInd = clusterTup[0], clusterTup[1]
                self.assertEqual(self.VclusExp.vecClus[vecListInd][clustInd], clust,
                                 msg="{} \n {}".format(self.VclusExp.vecClus[vecListInd][clustInd], clust))
                clusterCounts[clust] += 1
                clust2Tup[clust].append(clusterTup)

            for clust, count in clusterCounts.items():
                c = 0
                for site, spec in clust.SiteSpecs:
                    if site.ci == stSpc[0].ci and spec == stSpc[1]:
                        Rtrans = stSpc[0].R - site.R
                        if (self.VclusExp.vacSite, self.VclusExp.vacSpec) in [(site + Rtrans, spec)
                                                                              for site, spec in clust.SiteSpecs]:
                            if stSpc[0] != self.vacsite:
                                continue
                        c += 1
                # Now multiply the dimensionality of the vector basis

                dimBasis = 0
                for clustList in self.VclusExp.vecClus:
                    for cl in clustList:
                        if cl == clust:
                            dimBasis += 1

                self.assertEqual(c * dimBasis, count, msg="\nsite, species : {}\ncluster:{}\ncount:{}\n{}\ndimBasis:"
                                                          "{}\nc:{}".format(
                    stSpc, clust, count, clust2Tup[clust], dimBasis, c))

    def test_site_interactions(self):
        # test that every interaction is valid with the given Rtrans provided
        # The key site should be present only once
        interaction2RepClust = {}

        clust2Interact = collections.defaultdict(list)
        self.assertEqual(len(self.VclusExp.SiteSpecInteractions), self.NSpec*len(self.superBCC.mobilepos))
        for (key, infoList) in self.VclusExp.SiteSpecInteractions.items():
            clSite = key[0]
            sp = key[1]
            # print(infoList[0][0])
            for interactionData in infoList:
                interaction = interactionData[0]
                RepClust = interactionData[1]
                if not interaction in interaction2RepClust:
                    interaction2RepClust[interaction] = {RepClust}
                else:
                    interaction2RepClust[interaction].add(RepClust)
                clust2Interact[RepClust].append(interaction)
                count = 0
                for (site, spec) in interaction:
                    if site == clSite and sp == spec:
                        count += 1

                self.assertEqual(count, 1)
        self.assertEqual(len(clust2Interact), sum([len(clList) for clList in self.VclusExp.SpecClusters]),
                         msg="found:{}".format(len(clust2Interact)))

        for repClust, interactList in clust2Interact.items():
            for interaction in interactList:
                self.assertEqual(len(interaction2RepClust[interaction]), 1)
                self.assertTrue(repClust in interaction2RepClust[interaction])

    def testcluster2SpecClus(self):

        for clListInd, clList in enumerate(self.VclusExp.SpecClusters):
            for clustInd, clust in enumerate(clList):
                tup = self.VclusExp.clust2SpecClus[clust]
                self.assertEqual(tup[0], clListInd)
                self.assertEqual(tup[1], clustInd)

    def test_MC_step(self):
        """
        Here, we have to test an MC step to make sure the expansion is working properly.
        """
        # 1. set up energy coefficients
        EnCoeffs = np.random.rand(len(self.VclusExp.SpecClusters))

        # 2. set up KRA coefficients
        # Need to do this for each transition
        KRA_Coeff_List = {}
        for transition, clusterLists in self.VclusExp.KRAexpander.clusterSpeciesJumps.items():
            KRACoeffs = np.random.rand(len(clusterLists))
            KRA_Coeff_List[transition] = KRACoeffs

        beta = 1.0
        # Now perform an expansion with the random occupancy array we have defined
        # Expand(self, beta, mobOccs, EnCoeffs, KRACoeffs)
        start = time.time()
        Wbar, bbar = self.VclusExp.Expand(beta, self.mobOccs, EnCoeffs, KRA_Coeff_List)
        print(time.time() - start)

        





