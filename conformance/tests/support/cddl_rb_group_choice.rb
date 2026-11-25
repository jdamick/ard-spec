# Workaround for a crash in the reference CDDL tool (the `cddl` Ruby gem, 0.12.14).
#
# CDDL::Parser#grpent flattens the members of a named group (or of a map pulled in
# with `~`) into the enclosing map. A group choice among those members, as in
#
#   r = { a: tstr, rest }
#   rest = ( b: int, (u: tstr // d: int) )
#
# or AI Catalog's `CatalogEntry`, whose `(url: text // data: any)` is pulled in by
# `{ score: 0..100, ~CatalogEntry }`, reaches `fail t1.inspect unless t2[0] ==
# :grpent` and the tool exits with a RuntimeError. A choice that is the only entry of
# the group is already handled, and so is a choice written directly in the map.
#
# The map validator and generator already accept a `[:grpchoice, ...]` entry in a
# member list (it is what a choice written directly in a map becomes), so the fix is
# to pass such an entry through unchanged instead of failing.
#
# Loaded by conformance/tests/test_cddl.py through RUBYLIB and RUBYOPT=-rcddl_rb_group_choice. It changes
# nothing unless the installed gem is exactly 0.12.14, so a fixed release isn't
# overridden.

require "set"
gem "cddl"
require "cddl"

if Gem.loaded_specs["cddl"]&.version == Gem::Version.new("0.12.14")
  module CDDLGroupChoiceInGroupFix
    def grpent(n) # returns array of entries
      occ = occur(n.occur)
      if g = n.group || workaround1(n)
        gr = group(g)
        if occ != [1, 1]
          gr = [[:member, *occ, nil, [:grpent, *gr]]]
        end
        return gr
      end
      nt = n.type || (n.s && n.s.type) || (n.bareword && n.bareword.s.type) # workarounds
      unless nt
        warn "NO NT"
        warn @abnf.ast?
        fail ["ntype", n, n.children].inspect
      end
      if mk = n.memberkey # work around unclear bug in ast generation below
        if (t1 = mk.type1 || t1 = mk.value ||
                          ((t1 = mk.s) && (t1 = t1.type) && (t1 = t1.type1))) # workaround
          [[:member, *occ, type1(t1), type(nt)]]
        else
          bw = mk.bareword
          unless bw
            warn @abnf.ast?
            fail [n, n.children, mk, mk.children].inspect
          end
          name = bw.to_s
          [[:member, *occ, [:text, name.force_encoding(Encoding::UTF_8)], type(nt)]]
        end
      else
        t = if nbw = nt.bareword
              t1 = nbw.type1
              rest = type_collect(nt, true)
              s = [:type1, type1(t1, true), *rest]
              s.size == 2 ? s[1] : s # decapsulate single-element choice
            else
              type(nt, true) # type can actually be a group here!
            end
        pp ["t is", t] if ENV["CDDL_TRACE"]
        if t[0] == :grpent && (occ == [1, 1])
          # go through the members here and multiply the occs
          t1 = t[1..-1].flatten(1)
          if t1[0] == :recurse_grpent
            [t1]
          else
            # Changed: a group choice among the members is kept as a map entry, where
            # 0.12.14 failed unless it was the group's only entry.
            t1.flat_map { |t2|
              case t2[0]
              when :member, :grpchoice
                [t2]
              else
                fail t1.inspect unless t2[0] == :grpent
                t2[1..-1]
              end
            }.map { |mem|
              if mem[0] == :member
                mem[1] *= occ[0]
                mem[2] *= occ[1] # Does all the infinity magic
              end
              mem
            }
          end
        else
          if t[0] == :grpchoice && occ == [1, 1]
            [t]
          else
            if t[0] == :grpent
              t = [t[0], *t[1..-1].flatten(1)]
            end
            if occ[0] == 0 && t == [:grpchoice]
              [] # we won't be able to generate any of those
            else
              if t[0] == :grpchoice
                t = [:grpent, t]
              end
              [[:member, *occ, nil, t]]
            end
          end
        end
      end
    end
  end

  CDDL::Parser.prepend(CDDLGroupChoiceInGroupFix)
end
